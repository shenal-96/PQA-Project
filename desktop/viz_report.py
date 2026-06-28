"""Host-side report image renderer (hi-DPI matplotlib).

Produces the static PNG/JPEG images a generated report embeds — metric graphs,
the compliance-table image, and the per-event 4-panel snapshots — into the exact
on-disk layout that :func:`report.get_placeholder_map` scans by convention:

    <base_dir>/Graphs/<client>_<metric>.jpeg
    <base_dir>/Images/<client>_table.png
    <base_dir>/Snapshots/snap_<client>_<YYYYmmdd_HHMMSS>.jpeg

This reuses the validated renderers in the root ``visualizations.py`` (the same
code the live Streamlit app ships) so report images match what users already
trust. ``visualizations`` (and therefore matplotlib) is **imported lazily** so
this module stays cheap to import in contexts that never render — e.g. the CI
pytest job, which installs only pandas/numpy/pytest.

This is a host-only module (desktop). It never runs in the future iPad/Pyodide
path, which produces its charts in-browser from the JSON contract.
"""
from __future__ import annotations

import os

# The six processed metrics the default report template has placeholders for.
REPORT_METRICS = (
    "Avg_kW",
    "Avg_Voltage_LL",
    "Avg_Current",
    "Avg_Frequency",
    "Avg_PF",
    "Avg_THD_F",
)


def _remap_overrides(df_events, pos_overrides):
    """Translate positional-int override keys (0..n-1, as the frontend keys them)
    onto the df_events index labels that ``generate_all_snapshots`` looks up via
    ``iterrows()``. Returns None when there is nothing valid to apply.

    Keying by position then mapping through ``df_events.index[pos]`` keeps this
    correct regardless of whether df_events carries a default RangeIndex.
    """
    if not pos_overrides or df_events is None or df_events.empty:
        return None
    out = {}
    n = len(df_events)
    for k, v in pos_overrides.items():
        try:
            pos = int(k)
            val = float(v)
        except (TypeError, ValueError):
            continue
        if 0 <= pos < n:
            out[df_events.index[pos]] = val
    return out or None


def render_report_images(df_raw, df_proc, df_events, config, client_name,
                         base_dir, *, options=None,
                         snapshot_window_overrides=None,
                         snapshot_offset_overrides=None) -> dict:
    """Render every report image into ``base_dir`` and report what was produced.

    Parameters
    ----------
    df_raw      raw logger frame (3-phase columns) — drives the snapshots.
    df_proc     processed/averaged frame — drives the metric time-series graphs.
    df_events   detected-events frame — drives the table image and snapshots.
    config      ``AnalysisConfig`` used for the run (nominal V/F, tolerances, …).
    client_name filesystem-safe stem used in every output filename. Must match
                the ``client_name`` later handed to ``report.get_placeholder_map``.
    base_dir    working directory; ``Graphs/``, ``Images/``, ``Snapshots/`` are
                created beneath it.
    options     optional display overrides (see ``_OPTION_DEFAULTS``).
    snapshot_window_overrides / snapshot_offset_overrides
                optional per-event snapshot tweaks keyed by POSITIONAL event index
                (0..n-1, as the on-screen UI keys them). Remapped onto the
                df_events index here so the report's clean snapshots match the
                window/time-shift the user tuned per event (port of #21).

    Returns a dict with the three output dirs, the snapshot count, and a list of
    non-fatal error strings (image rendering is best-effort: one failed plot must
    not sink the whole report).
    """
    import visualizations as viz  # lazy: pulls in matplotlib

    opts = {**_OPTION_DEFAULTS, **(options or {})}
    # "Remove warnings from report": clear the not-recovered flags before rendering
    # so the snapshots drop the red watermark/tint (the analysis numbers are
    # untouched — only the report imagery changes).
    if opts.get("clear_not_recovered") and df_events is not None and not df_events.empty:
        df_events = df_events.copy()
        for _col in ("V_not_recovered", "F_not_recovered"):
            if _col in df_events.columns:
                df_events[_col] = False
    graph_dir = os.path.join(base_dir, "Graphs")
    snapshot_dir = os.path.join(base_dir, "Snapshots")
    image_dir = os.path.join(base_dir, "Images")
    for d in (graph_dir, snapshot_dir, image_dir):
        os.makedirs(d, exist_ok=True)

    errors: list[str] = []
    nom_v = float(config.nominal_voltage)
    nom_f = float(config.nominal_frequency)
    rated = options.get("rated_load_kw") if options else None

    # Asymmetric max-deviation limits mirror the Streamlit report path: the upper
    # limit uses the load-decrease tolerance, the lower limit the load-increase one
    # (see app.py plot_kwargs). The symmetric *_max_dev values are the fallback the
    # snapshot renderer falls back to when an event row carries no per-event pct.
    v_max_dev = float(getattr(config, "voltage_max_deviation_pct", 15.0))
    f_max_dev = float(getattr(config, "frequency_max_deviation_pct", 7.0))

    # ── Metric time-series graphs ──────────────────────────────────────────────
    try:
        _paths, _errs = viz.generate_plots(
            df_proc, client_name, output_dir=graph_dir,
            metric_keys=list(REPORT_METRICS),
            show_limits=opts["show_limits"],
            nom_v=nom_v, nom_f=nom_f,
            tol_v=float(config.voltage_tolerance_pct),
            tol_f=float(config.frequency_tolerance_pct),
            v_max_dev=v_max_dev, f_max_dev=f_max_dev,
            v_max_dev_upper=float(getattr(config, "volt_max_dev_pct_decrease", v_max_dev)),
            v_max_dev_lower=float(getattr(config, "volt_max_dev_pct_increase", v_max_dev)),
            f_max_dev_upper=float(getattr(config, "freq_max_dev_pct_decrease", f_max_dev)),
            f_max_dev_lower=float(getattr(config, "freq_max_dev_pct_increase", f_max_dev)),
        )
        errors.extend(_errs or [])
    except Exception as exc:  # noqa: BLE001 — best-effort image rendering
        errors.append(f"Metric graphs failed: {exc}")

    # ── Compliance table image ─────────────────────────────────────────────────
    if df_events is not None and not df_events.empty:
        try:
            table_file = os.path.join(image_dir, f"{client_name}_table.png")
            viz.save_compliance_table_as_image(
                df_events, table_file, client_name,
                nom_v=nom_v, nom_f=nom_f, rated_load_kw=rated,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Compliance table failed: {exc}")

    # ── ITIC (CBEMA) curve ─────────────────────────────────────────────────────
    # Opt-in (report toggle): plot_itic_curve writes both an SVG and a JPEG; we
    # use the JPEG since python-docx/HTML embed raster, not SVG.
    itic_path = None
    if opts.get("include_itic") and df_events is not None and not df_events.empty:
        try:
            viz.plot_itic_curve(df_events, client_name, nom_v=nom_v,
                                output_dir=graph_dir)
            cand = os.path.join(graph_dir, f"{client_name}_ITIC_Curve.jpeg")
            itic_path = cand if os.path.exists(cand) else None
            if itic_path is None:
                errors.append("ITIC curve produced no plottable events.")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"ITIC curve failed: {exc}")

    # ── Per-event snapshots ────────────────────────────────────────────────────
    n_snapshots = 0
    if df_events is not None and not df_events.empty:
        try:
            paths, snap_errs = viz.generate_all_snapshots(
                df_raw, df_events, client_name, output_dir=snapshot_dir,
                show_limits=opts["show_limits"],
                show_tolerance_band=opts["show_tolerance_band"],
                show_deviation_limits=opts["show_deviation_limits"],
                nom_v=nom_v, nom_f=nom_f,
                tol_v=float(config.voltage_tolerance_pct),
                tol_f=float(config.frequency_tolerance_pct),
                v_max_dev=v_max_dev, f_max_dev=f_max_dev,
                show_debug=False,
                show_intersections=opts["show_intersections"],
                show_max_deviation=opts["show_max_deviation"],
                rated_load_kw=rated,
                window_s=float(config.snapshot_window_s),
                window_overrides=_remap_overrides(df_events, snapshot_window_overrides),
                offset_overrides=_remap_overrides(df_events, snapshot_offset_overrides),
            )
            errors.extend(snap_errs or [])
            n_snapshots = sum(1 for p in paths if p)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Snapshots failed: {exc}")

    return {
        "graph_dir": graph_dir,
        "snapshot_dir": snapshot_dir,
        "image_dir": image_dir,
        "itic_path": itic_path,
        "n_snapshots": n_snapshots,
        "errors": errors,
    }


# Default display options for the clean report look (mirrors the Streamlit
# report-generation path: limit lines on, no debug/intersection clutter).
_OPTION_DEFAULTS = {
    "show_limits": True,            # draw max-deviation limit lines on V/F graphs
    "show_tolerance_band": True,    # amber recovery band on snapshots
    "show_deviation_limits": True,  # red direction-relevant max-dev line on snapshots
    "show_intersections": False,    # exit/recovery stars — off for a clean report
    "show_max_deviation": False,    # extreme marker — off for a clean report
    "clear_not_recovered": False,   # drop the not-recovered watermark/tint
    "include_itic": False,          # render the ITIC (CBEMA) curve for the report
}
