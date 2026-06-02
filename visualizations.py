"""
Visualization functions for Power Quality Analysis.

Generates time-series plots, event snapshots, and compliance table images.
All functions return matplotlib figures or file paths - no UI dependencies.
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.patches import FancyArrowPatch
import pandas as pd
import numpy as np


# ── Design tokens (match app CSS) ────────────────────────────────────────────
_NAVY       = "#0f172a"
_SLATE      = "#1e293b"
_BLUE       = "#2563eb"
_BLUE_LIGHT = "#93c5fd"
_GREEN      = "#16a34a"
_RED        = "#dc2626"
_ORANGE     = "#ea580c"
_CYAN       = "#0891b2"
_PURPLE     = "#9333ea"
_AMBER      = "#f59e0b"   # debug: event detection markers
_LIME       = "#10b981"   # debug: recovery crossing markers
_GRID       = "#e2e8f0"
_TEXT_MAIN  = "#0f172a"
_TEXT_SUB   = "#64748b"
_BG         = "#ffffff"

def _style_ax(ax, ylabel, color):
    """Apply consistent axis styling for print-quality technical reports."""
    ax.set_facecolor(_BG)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_GRID)
    ax.spines["bottom"].set_color(_GRID)
    ax.spines["left"].set_linewidth(1.2)
    ax.spines["bottom"].set_linewidth(1.2)
    ax.tick_params(colors=_TEXT_SUB, labelsize=11, width=1.0, length=4)
    ax.set_ylabel(ylabel, fontsize=13, color=_TEXT_MAIN, fontweight="600", labelpad=10)
    ax.yaxis.set_label_position("left")
    ax.grid(True, color=_GRID, linewidth=1.0, linestyle="-", alpha=0.7)
    ax.grid(True, which="minor", color=_GRID, linewidth=0.5, alpha=0.3)
    ax.set_axisbelow(True)


def generate_plots(df_proc, client_name, output_dir="output/Graphs",
                   show_limits=False, nom_v=415.0, nom_f=50.0,
                   tol_v=1.0, tol_f=0.5, v_max_dev=15.0, f_max_dev=7.0,
                   v_max_dev_upper=None, v_max_dev_lower=None,
                   f_max_dev_upper=None, f_max_dev_lower=None,
                   metric_keys=None,
                   show_debug=False, show_intersections=False, df_events=None, thresh_kw=50.0):
    """
    Generate time-series plots for available metrics.

    Parameters:
        metric_keys:  optional list of metric column names to generate (default: all)
        show_debug:   overlay event-detection and recovery-crossing markers for debugging
        df_events:    events DataFrame (required when show_debug=True)
        thresh_kw:    load detection threshold in kW (shown on Avg_kW plot when debugging)

    Returns:
        tuple: (paths dict, errors list)
    """
    os.makedirs(output_dir, exist_ok=True)
    paths = {}
    plot_errors = []

    metrics = {
        "Avg_kW":          ("Power (kW)",         _GREEN),
        "Avg_Voltage_LL": ("Voltage (L-L)",       _BLUE),
        "Avg_Current":     ("Current (A)",        _RED),
        "Avg_Frequency":   ("Frequency (Hz)",     _ORANGE),
        "Avg_PF":          ("Power Factor",       _CYAN),
        "Avg_THD_F":       ("THD (%)",            _PURPLE),
    }

    if metric_keys is not None:
        metrics = {k: v for k, v in metrics.items() if k in metric_keys}

    for col, (ylabel, color) in metrics.items():
        if col not in df_proc.columns or df_proc[col].dropna().empty:
            continue

        fig, ax = plt.subplots(figsize=(14, 4))
        fig.patch.set_facecolor(_BG)

        y = df_proc[col]
        x = df_proc["Timestamp"]

        # Area fill
        ax.fill_between(x, y, y.min(), color=color, alpha=0.08)
        # Main line
        ax.plot(x, y, color=color, linewidth=2.0, solid_capstyle="round")

        _style_ax(ax, ylabel, color)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        fig.autofmt_xdate(rotation=0, ha="center")
        ax.tick_params(axis="x", labelsize=11, colors=_TEXT_SUB)

        if show_limits:
            limit_kw = dict(linewidth=1.5, alpha=0.7, zorder=3)
            if col == "Avg_Voltage_LL":
                _vup = v_max_dev_upper if v_max_dev_upper is not None else v_max_dev
                _vlo = v_max_dev_lower if v_max_dev_lower is not None else v_max_dev
                upper = nom_v * (1 + _vup / 100)
                lower = nom_v * (1 - _vlo / 100)
                ax.axhline(upper, color=_RED, ls="--", label=f"Max dev +{_vup}% ({upper:.1f}V)", **limit_kw)
                ax.axhline(lower, color=_RED, ls="--", label=f"Max dev -{_vlo}% ({lower:.1f}V)", **limit_kw)
                ax.legend(fontsize=10, framealpha=0.9, loc="upper right", edgecolor=_GRID)
            elif col == "Avg_Frequency":
                _fup = f_max_dev_upper if f_max_dev_upper is not None else f_max_dev
                _flo = f_max_dev_lower if f_max_dev_lower is not None else f_max_dev
                upper = nom_f * (1 + _fup / 100)
                lower = nom_f * (1 - _flo / 100)
                ax.axhline(upper, color=_RED, ls="--", label=f"Max dev +{_fup}% ({upper:.3f}Hz)", **limit_kw)
                ax.axhline(lower, color=_RED, ls="--", label=f"Max dev -{_flo}% ({lower:.3f}Hz)", **limit_kw)
                ax.legend(fontsize=10, framealpha=0.9, loc="upper right", edgecolor=_GRID)

        # ── Debug overlay ────────────────────────────────────────────────────
        if show_debug and df_events is not None and not df_events.empty:
            ev_line_kw  = dict(linewidth=1.0, linestyle=":", zorder=5, alpha=0.85)
            cross_line_kw = dict(linewidth=1.0, linestyle=":", zorder=5, alpha=0.85)

            if col == "Avg_kW":
                # Dotted horizontal threshold band centred on each event's pre-event kW.
                # Also mark each event with a vertical amber line and dKw annotation.
                ax.axhline(thresh_kw, color=_AMBER, linewidth=1.0, linestyle=":",
                           alpha=0.6, label=f"±{thresh_kw:.0f} kW threshold")
                ax.axhline(-thresh_kw, color=_AMBER, linewidth=1.0, linestyle=":",
                           alpha=0.6)
                for _, ev in df_events.iterrows():
                    ax.axvline(ev["Timestamp"], color=_AMBER, **ev_line_kw)
                    ylim = ax.get_ylim()
                    ax.text(
                        ev["Timestamp"], ylim[1] * 0.92,
                        f"  dKw={ev.get('dKw', 0):+.0f}kW",
                        fontsize=7, color=_AMBER, va="top", rotation=90,
                        fontweight="600",
                    )
                ax.legend(fontsize=7, framealpha=0.9, loc="upper right")

            elif col == "Avg_Voltage_LL":
                upper = nom_v * (1 + tol_v / 100)
                lower = nom_v * (1 - tol_v / 100)
                # Always draw the band limits in debug mode (dotted amber)
                if not show_limits:
                    ax.axhline(upper, color=_AMBER, linewidth=1.1, linestyle=":",
                               alpha=0.7, label=f"+{tol_v}% ({upper:.1f}V)")
                    ax.axhline(lower, color=_AMBER, linewidth=1.1, linestyle=":",
                               alpha=0.7, label=f"-{tol_v}% ({lower:.1f}V)")
                for _, ev in df_events.iterrows():
                    # Amber vertical at load-change detection point
                    ax.axvline(ev["Timestamp"], color=_AMBER, **ev_line_kw)
                    v_dev = ev.get("V_dev", np.nan)
                    band_val = upper if (pd.notnull(v_dev) and v_dev > nom_v) else lower
                    # Orange ★ at exact V exit crossing
                    v_exit = ev.get("V_exit_ts")
                    if pd.notnull(v_exit):
                        ax.axvline(v_exit, color=_ORANGE, **ev_line_kw)
                        ax.scatter([v_exit], [band_val],
                                   color=_ORANGE, marker="*", s=120, zorder=7,
                                   label="V exit band")
                        ax.annotate(
                            "exit",
                            xy=(v_exit, band_val),
                            xytext=(4, -12), textcoords="offset points",
                            fontsize=7, color=_ORANGE, fontweight="700",
                        )
                    # Lime ★ at exact V re-entry crossing
                    v_rec = ev.get("V_rec_s")
                    if pd.notnull(v_rec) and pd.notnull(v_exit):
                        cross_ts = v_exit + pd.Timedelta(seconds=float(v_rec))
                        ax.axvline(cross_ts, color=_LIME, **cross_line_kw)
                        ax.scatter([cross_ts], [band_val],
                                   color=_LIME, marker="*", s=120, zorder=7,
                                   label=f"V recovery {v_rec:.2f}s")
                        ax.annotate(
                            f"{v_rec:.2f}s",
                            xy=(cross_ts, band_val),
                            xytext=(4, 6), textcoords="offset points",
                            fontsize=7, color=_LIME, fontweight="700",
                        )
                ax.legend(fontsize=7, framealpha=0.9, loc="upper right")

            elif col == "Avg_Frequency":
                # In debug mode draw the per-event asymmetric recovery bands.
                # Each event may have a different upper/lower depending on load direction,
                # so draw individual band lines per event rather than a single global pair.
                for _, ev in df_events.iterrows():
                    f_upper = ev.get("F_rec_upper", nom_f * (1 + tol_f / 100))
                    f_lower = ev.get("F_rec_lower", nom_f * (1 - tol_f / 100))
                    if pd.isnull(f_upper):
                        f_upper = nom_f * (1 + tol_f / 100)
                    if pd.isnull(f_lower):
                        f_lower = nom_f * (1 - tol_f / 100)

                    # Show band limits as amber dotted lines if not already via show_limits
                    if not show_limits:
                        ax.axhline(f_upper, color=_AMBER, linewidth=1.1, linestyle=":",
                                   alpha=0.6)
                        ax.axhline(f_lower, color=_AMBER, linewidth=1.1, linestyle=":",
                                   alpha=0.6)

                    f_dev = ev.get("F_dev", np.nan)
                    # Determine which boundary the signal crossed at exit/re-entry
                    band_val = f_upper if (pd.notnull(f_dev) and f_dev > nom_f) else f_lower

                    ax.axvline(ev["Timestamp"], color=_AMBER, **ev_line_kw)
                    f_exit = ev.get("F_exit_ts")
                    if pd.notnull(f_exit):
                        ax.axvline(f_exit, color=_ORANGE, **ev_line_kw)
                        ax.scatter([f_exit], [band_val],
                                   color=_ORANGE, marker="*", s=120, zorder=7)
                        ax.annotate(
                            "exit",
                            xy=(f_exit, band_val),
                            xytext=(4, -12), textcoords="offset points",
                            fontsize=7, color=_ORANGE, fontweight="700",
                        )
                    f_rec = ev.get("F_rec_s")
                    if pd.notnull(f_rec) and pd.notnull(f_exit):
                        cross_ts = f_exit + pd.Timedelta(seconds=float(f_rec))
                        ax.axvline(cross_ts, color=_LIME, **cross_line_kw)
                        ax.scatter([cross_ts], [band_val],
                                   color=_LIME, marker="*", s=120, zorder=7)
                        ax.annotate(
                            f"{f_rec:.2f}s",
                            xy=(cross_ts, band_val),
                            xytext=(4, 6), textcoords="offset points",
                            fontsize=7, color=_LIME, fontweight="700",
                        )

                # Single legend entry showing which band applies to which direction
                from matplotlib.lines import Line2D
                legend_items = [
                    Line2D([0], [0], color=_AMBER, ls=":", lw=1.1, label="recovery band"),
                    Line2D([0], [0], color=_ORANGE, marker="*", ls="none",
                           markersize=8, label="F exit band"),
                    Line2D([0], [0], color=_LIME, marker="*", ls="none",
                           markersize=8, label="F recovery"),
                ]
                ax.legend(handles=legend_items, fontsize=7, framealpha=0.9, loc="upper right")

            else:
                # All other metrics: just amber vertical lines at event timestamps
                for _, ev in df_events.iterrows():
                    ax.axvline(ev["Timestamp"], color=_AMBER, **ev_line_kw)

        # Title block — main title sits above the client name subtitle
        ax.set_title(ylabel, fontsize=16, fontweight="700",
                     color=_TEXT_MAIN, pad=24, loc="left")
        fig.text(0.01, 1.01, client_name, transform=ax.transAxes,
                 fontsize=11, color=_TEXT_SUB, va="bottom")

        fig.tight_layout(pad=1.2)
        fname = os.path.join(output_dir, f"{client_name}_{col}.svg")
        fig.savefig(fname, format="svg", bbox_inches="tight", facecolor=_BG)
        # Save a taller JPEG for Word/PDF report insertion (SVG cannot be embedded in docx).
        # Re-render at a 16×6 figure — wider aspect ratio reads much better on paper
        # than the 14×4 screen ratio. tight_layout is re-applied after the resize so
        # axis labels and titles re-flow correctly at the new dimensions.
        fig.set_size_inches(16, 6)
        fig.tight_layout(pad=1.2)
        jpeg_fname = os.path.join(output_dir, f"{client_name}_{col}.jpeg")
        fig.savefig(jpeg_fname, format="jpeg", dpi=200, bbox_inches="tight", facecolor=_BG)
        plt.close(fig)
        paths[col] = fname

    return paths, plot_errors


def plot_detected_events(df_proc, df_events, client_name, output_dir="output/Graphs",
                         thresh_kw=50.0):
    """
    Render a Power (kW) time-series plot with each detected load-step event
    overlaid as a vertical marker plus its dKw label. Mirrors the styling of
    `generate_plots` for Avg_kW so the visual matches the rest of the
    time-series tabs, but the event overlay is always drawn (not only in
    debug mode).

    Returns the saved SVG path, or None if df_proc has no Avg_kW data.
    """
    if "Avg_kW" not in df_proc.columns or df_proc["Avg_kW"].dropna().empty:
        return None

    os.makedirs(output_dir, exist_ok=True)

    fig, ax = plt.subplots(figsize=(14, 4))
    fig.patch.set_facecolor(_BG)

    y = df_proc["Avg_kW"]
    x = df_proc["Timestamp"]
    ax.fill_between(x, y, y.min(), color=_GREEN, alpha=0.08)
    ax.plot(x, y, color=_GREEN, linewidth=2.0, solid_capstyle="round")

    _style_ax(ax, "Power (kW)", _GREEN)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.autofmt_xdate(rotation=0, ha="center")
    ax.tick_params(axis="x", labelsize=11, colors=_TEXT_SUB)

    # ── Detected-event overlay ──────────────────────────────────────────────
    n_events = 0
    if df_events is not None and not df_events.empty:
        for _, ev in df_events.iterrows():
            ax.axvline(ev["Timestamp"], color=_AMBER, linewidth=1.2,
                       linestyle=":", alpha=0.9, zorder=5)
        ylim = ax.get_ylim()
        for _, ev in df_events.iterrows():
            dkw = ev.get("dKw", 0)
            ax.text(
                ev["Timestamp"], ylim[1] * 0.96,
                f"  {dkw:+.0f} kW",
                fontsize=8, color=_AMBER, va="top", rotation=90,
                fontweight="600",
            )
        ax.set_ylim(ylim)
        n_events = len(df_events)

    from matplotlib.lines import Line2D
    legend_items = [
        Line2D([0], [0], color=_GREEN, lw=2.0, label="Power (kW)"),
        Line2D([0], [0], color=_AMBER, ls=":", lw=1.2,
               label=f"Detected event ({n_events})"),
    ]
    ax.legend(handles=legend_items, fontsize=10, framealpha=0.9,
              loc="upper right", edgecolor=_GRID)

    ax.set_title("Detected Events", fontsize=16, fontweight="700",
                 color=_TEXT_MAIN, pad=24, loc="left")
    fig.text(0.01, 1.01, client_name, transform=ax.transAxes,
             fontsize=11, color=_TEXT_SUB, va="bottom")

    fig.tight_layout(pad=1.2)
    fname = os.path.join(output_dir, f"{client_name}_Detected_Events.svg")
    fig.savefig(fname, format="svg", bbox_inches="tight", facecolor=_BG)
    fig.set_size_inches(16, 6)
    fig.tight_layout(pad=1.2)
    jpeg_fname = os.path.join(output_dir, f"{client_name}_Detected_Events.jpeg")
    fig.savefig(jpeg_fname, format="jpeg", dpi=200, bbox_inches="tight", facecolor=_BG)
    plt.close(fig)
    return fname


# ── Temperature / Pressure column groups ─────────────────────────────────────
_TP_GROUPS = {
    "Pressures": {
        "cols":   ["P-Oil", "P-Intake"],
        "labels": {"P-Oil": "Oil Pressure", "P-Intake": "Intake Pressure"},
        "ylabel": "Pressure",
        "colors": [_CYAN, _BLUE],
    },
    "Engine_Temps": {
        "cols":   ["T-Fuel", "T-Oil", "T-Coolant", "T-IntManifold", "T-Intcooler", "T-ECU"],
        "labels": {"T-Fuel": "Fuel", "T-Oil": "Oil", "T-Coolant": "Coolant",
                   "T-IntManifold": "Int. Manifold", "T-Intcooler": "Intercooler", "T-ECU": "ECU"},
        "ylabel": "Temperature (°C)",
        "colors": [_RED, _ORANGE, _CYAN, _AMBER, _PURPLE, _GREEN],
    },
    "Generator_Temps": {
        "cols":   ["Generator Winding (Temp 1A-U)", "Generator Winding (Temp 2A-V)",
                   "Generator Winding (Temp 3A-W)", "Generator Bearing Temp (NDE)"],
        "labels": {"Generator Winding (Temp 1A-U)": "Winding U",
                   "Generator Winding (Temp 2A-V)": "Winding V",
                   "Generator Winding (Temp 3A-W)": "Winding W",
                   "Generator Bearing Temp (NDE)":  "Bearing (NDE)"},
        "ylabel": "Temperature (°C)",
        "colors": [_BLUE, _RED, _GREEN, _ORANGE],
    },
}


# ── ITIC / CBEMA curve ───────────────────────────────────────────────────────
# Standard ITIC envelope (% of nominal voltage vs event duration in seconds).
# Each tuple = (start_s, end_s, percent). Vertical step transitions are implicit
# at segment boundaries.
_ITIC_UPPER = [
    (1e-4, 1e-3, 500),
    (1e-3, 3e-3, 200),
    (3e-3, 0.5,  140),
    (0.5,  10,   120),
    (10,   1e3,  110),
]
_ITIC_LOWER = [
    (1e-4, 0.02, 0),
    (0.02, 0.5,  70),
    (0.5,  10,   80),
    (10,   1e3,  90),
]


def _itic_envelope_at(x_s, segments):
    """Return the envelope % at duration x_s using the stepped segment list."""
    for a, b, y in segments:
        if a <= x_s <= b:
            return y
    if x_s < segments[0][0]:
        return segments[0][2]
    return segments[-1][2]


def _itic_polyline(segments):
    """Convert stepped segment list into (xs, ys) for plotting."""
    xs, ys = [], []
    for i, (a, b, y) in enumerate(segments):
        xs.extend([a, b])
        ys.extend([y, y])
        if i + 1 < len(segments):
            # Vertical riser at segment boundary (b == next_a).
            xs.append(b)
            ys.append(segments[i + 1][2])
    return xs, ys


def plot_itic_curve(df_events, client_name, nom_v=415.0,
                    output_dir="output/Graphs"):
    """
    Plot the ITIC (CBEMA) compatibility curve with detected events overlaid.

    X-axis: event duration (s, log scale) — taken from V_rec_s.
    Y-axis: voltage during event as % of nominal — taken from V_dev / nom_v * 100.

    Only events with both V_exit_ts and V_rec_s are plotted (events that actually
    left the tolerance band and recovered within the recorded data).

    Returns:
        str | None: path to saved SVG, or None if df_events is empty / no plottable events.
    """
    os.makedirs(output_dir, exist_ok=True)

    if df_events is None or df_events.empty:
        plottable = pd.DataFrame()
    else:
        cols_needed = {"V_dev", "V_rec_s", "V_exit_ts"}
        if not cols_needed.issubset(df_events.columns):
            return None
        mask = df_events["V_exit_ts"].notna() & df_events["V_rec_s"].notna() & df_events["V_dev"].notna()
        plottable = df_events.loc[mask].copy()

    fig, ax = plt.subplots(figsize=(14, 5.5), facecolor=_BG)
    _style_ax(ax, "Voltage (% of nominal)", _TEXT_MAIN)
    ax.set_xscale("log")
    ax.set_xlim(1e-3, 1e3)
    ax.set_ylim(0, 250)
    ax.set_xlabel("Event duration (s)", fontsize=13, color=_TEXT_MAIN,
                  fontweight="600", labelpad=10)

    upper_x, upper_y = _itic_polyline(_ITIC_UPPER)
    lower_x, lower_y = _itic_polyline(_ITIC_LOWER)

    # Region shading. Three polygons across the full x-range.
    x_min, x_max = 1e-3, 1e3
    y_top = 250
    # Prohibited (above upper envelope).
    ax.fill_between(upper_x, upper_y, y_top, color=_RED, alpha=0.10,
                    step=None, linewidth=0, zorder=0)
    # No-Damage (below lower envelope).
    ax.fill_between(lower_x, 0, lower_y, color=_BLUE, alpha=0.08,
                    step=None, linewidth=0, zorder=0)
    # No-Interruption (between envelopes) — built by stitching the two polylines.
    poly_x = list(upper_x) + list(reversed(lower_x))
    poly_y = list(upper_y) + list(reversed(lower_y))
    ax.fill(poly_x, poly_y, color=_GREEN, alpha=0.08, linewidth=0, zorder=0)

    # Envelope lines.
    ax.plot(upper_x, upper_y, color=_RED, linewidth=2.0, zorder=2,
            label="ITIC upper limit (overvoltage)")
    ax.plot(lower_x, lower_y, color=_BLUE, linewidth=2.0, zorder=2,
            label="ITIC lower limit (undervoltage)")

    # Nominal reference at 100%.
    ax.axhline(100, color=_TEXT_SUB, linewidth=1.0, linestyle=":", alpha=0.6, zorder=1)

    # Region labels.
    ax.text(0.5, 230, "Prohibited region", color=_RED, fontsize=11,
            fontweight="600", ha="center", va="center", alpha=0.85)
    ax.text(0.5, 100, "No-interruption region", color=_GREEN, fontsize=11,
            fontweight="600", ha="center", va="center", alpha=0.85)
    ax.text(0.5, 35, "No-damage region", color=_BLUE, fontsize=11,
            fontweight="600", ha="center", va="center", alpha=0.85)

    # Event scatter.
    inside_x, inside_y, outside_x, outside_y = [], [], [], []
    for _, row in plottable.iterrows():
        dur = float(row["V_rec_s"])
        pct = float(row["V_dev"]) / nom_v * 100.0
        if dur <= 0 or not np.isfinite(dur) or not np.isfinite(pct):
            continue
        upper_pct = _itic_envelope_at(dur, _ITIC_UPPER)
        lower_pct = _itic_envelope_at(dur, _ITIC_LOWER)
        if lower_pct <= pct <= upper_pct:
            inside_x.append(dur)
            inside_y.append(pct)
        else:
            outside_x.append(dur)
            outside_y.append(pct)

    if inside_x:
        ax.scatter(inside_x, inside_y, s=70, color=_GREEN, edgecolor=_NAVY,
                   linewidth=1.0, zorder=4,
                   label=f"Compliant events ({len(inside_x)})")
    if outside_x:
        ax.scatter(outside_x, outside_y, s=90, color=_RED, edgecolor=_NAVY,
                   linewidth=1.0, marker="X", zorder=5,
                   label=f"ITIC violations ({len(outside_x)})")

    ax.legend(loc="upper right", fontsize=10, frameon=True, facecolor="white",
              edgecolor=_GRID)

    title = f"ITIC (CBEMA) Curve — {client_name}"
    ax.set_title(title, fontsize=15, color=_TEXT_MAIN, fontweight="700",
                 pad=14, loc="left")

    # Sampling-resolution caveat.
    ax.text(0.01, -0.18,
            "Note: 1 Hz logger sampling cannot resolve sub-second events. "
            "Only events with detected band exit and recovery are plotted.",
            transform=ax.transAxes, fontsize=9, color=_TEXT_SUB,
            ha="left", va="top", style="italic")

    fig.tight_layout(pad=1.2)
    fname = os.path.join(output_dir, f"{client_name}_ITIC_Curve.svg")
    fig.savefig(fname, format="svg", bbox_inches="tight", facecolor=_BG)
    jpeg_fname = os.path.join(output_dir, f"{client_name}_ITIC_Curve.jpeg")
    fig.savefig(jpeg_fname, format="jpeg", dpi=200, bbox_inches="tight",
                facecolor=_BG)
    plt.close(fig)
    return fname


def generate_temp_pressure_plots(df, client_name, output_dir="output/Graphs"):
    """
    Generate temperature and pressure time-series plots from WinScope data.
    Returns dict mapping group key -> SVG file path. Groups with no present columns are skipped.
    """
    os.makedirs(output_dir, exist_ok=True)
    paths = {}

    for group_key, grp in _TP_GROUPS.items():
        present = [c for c in grp["cols"] if c in df.columns and not df[c].dropna().empty]
        if not present:
            continue

        fig, ax = plt.subplots(figsize=(14, 4))
        fig.patch.set_facecolor(_BG)

        x = df["Timestamp"]
        for i, col in enumerate(present):
            color = grp["colors"][i % len(grp["colors"])]
            y = pd.to_numeric(df[col], errors="coerce")
            ax.plot(x, y, color=color, linewidth=2.0, solid_capstyle="round",
                    label=grp["labels"].get(col, col))

        _style_ax(ax, grp["ylabel"], _TEXT_MAIN)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        fig.autofmt_xdate(rotation=0, ha="center")
        ax.tick_params(axis="x", labelsize=11, colors=_TEXT_SUB)
        ax.legend(fontsize=10, framealpha=0.9, loc="upper right",
                  edgecolor=_GRID, facecolor=_BG)

        ax.set_title(group_key.replace("_", " "), fontsize=16, fontweight="700",
                     color=_TEXT_MAIN, pad=24, loc="left")
        fig.text(0.01, 1.01, client_name, transform=ax.transAxes,
                 fontsize=11, color=_TEXT_SUB, va="bottom")

        fig.tight_layout(pad=1.2)
        fname = os.path.join(output_dir, f"{client_name}_{group_key}.svg")
        fig.savefig(fname, format="svg", bbox_inches="tight", facecolor=_BG)
        fig.set_size_inches(16, 6)
        fig.tight_layout(pad=1.2)
        fig.savefig(os.path.join(output_dir, f"{client_name}_{group_key}.jpeg"),
                    format="jpeg", dpi=200, bbox_inches="tight", facecolor=_BG)
        plt.close(fig)
        paths[group_key] = fname

    return paths


def plot_load_change_snapshot(df_raw, event_ts, load_change, load_before, load_after,
                              client_name, output_dir="output/Snapshots",
                              show_limits=False, show_tolerance_band=True, show_deviation_limits=True,
                              nom_v=415.0, nom_f=50.0, tol_v=1.0, tol_f=0.5,
                              v_max_dev=15.0, f_max_dev=7.0,
                              show_debug=False, show_intersections=False, event_row=None,
                              show_max_deviation=False,
                              rated_load_kw=None, window_s=10,
                              next_event_ts=None, prev_event_ts=None,
                              time_offset_s=0.0):
    """
    Generate a +-5 second snapshot around a load event showing V, I, F, kW.

    Parameters:
        show_debug:  overlay band-exit (orange ★) and recovery (lime ★) crossings.
        event_row:   Series/dict with V_exit_ts, V_rec_s, F_exit_ts, F_rec_s,
                     V_dev, F_dev, F_rec_upper, F_rec_lower (required when show_debug=True).

    Returns:
        str: file path of saved snapshot image
    """
    os.makedirs(output_dir, exist_ok=True)

    # Determine time bounds: window_s is the TOTAL span (e.g. 8 -> -4s..+4s),
    # but extend if intersection markers (exit / recovery) fall outside.
    half_window = window_s / 2.0
    # time_offset_s shifts the window forward (+) or backward (-) along the
    # time axis while keeping the event marker at its true timestamp. The
    # event sits at relative t=0 still — we just show more pre- or post-
    # event data depending on the sign of the offset.
    left_s = half_window - float(time_offset_s)
    right_s = half_window + float(time_offset_s)
    # Guard against degenerate windows when offset > half_window.
    if left_s < 0.5:
        left_s = 0.5
    if right_s < 0.5:
        right_s = 0.5
    if show_intersections and event_row is not None:
        for exit_key, rec_key in [("V_exit_ts", "V_rec_s"), ("F_exit_ts", "F_rec_s")]:
            ex = event_row.get(exit_key)
            rc = event_row.get(rec_key)
            # Extend left to include exit marker
            if pd.notnull(ex):
                needed_left = (event_ts - pd.Timestamp(ex)).total_seconds() + 2
                if needed_left > left_s:
                    left_s = needed_left
            # Extend right to include recovery marker
            if pd.notnull(ex) and pd.notnull(rc):
                marker_ts = pd.Timestamp(ex) + pd.Timedelta(seconds=float(rc))
                needed_right = (marker_ts - event_ts).total_seconds() + 2
                if needed_right > right_s:
                    right_s = needed_right

    # Hard ceiling: never extend past neighbouring events. Otherwise a far-out
    # recovery marker drags the next event's data into this snapshot, inflating
    # load_before / load_after and producing a misleading wide x-axis.
    # Skipped when the user has explicitly shifted the window — that is a
    # deliberate override and should be respected even if it overlaps neighbours.
    _explicit_shift = abs(float(time_offset_s)) > 1e-9
    if not _explicit_shift and next_event_ts is not None and pd.notnull(next_event_ts):
        max_right = (pd.Timestamp(next_event_ts) - event_ts).total_seconds()
        if max_right > 0:
            right_s = min(right_s, max_right)
    if not _explicit_shift and prev_event_ts is not None and pd.notnull(prev_event_ts):
        max_left = (event_ts - pd.Timestamp(prev_event_ts)).total_seconds()
        if max_left > 0:
            left_s = min(left_s, max_left)

    df_win = df_raw[
        (df_raw["Timestamp"] >= event_ts - pd.Timedelta(seconds=left_s)) &
        (df_raw["Timestamp"] <= event_ts + pd.Timedelta(seconds=right_s))
    ].copy()

    if df_win.empty:
        return None

    # Derive actual before/after load from the data window for an accurate title.
    if "P_sum_AVG" in df_win.columns:
        kw_win = pd.to_numeric(df_win["P_sum_AVG"], errors="coerce") / 1000
        pre_mask  = df_win["Timestamp"] < event_ts
        post_mask = df_win["Timestamp"] > event_ts + pd.Timedelta(seconds=1)
        pre_vals  = kw_win[pre_mask]
        post_vals = kw_win[post_mask]
        if not pre_vals.empty and not post_vals.empty:
            load_before = pre_vals.mean()
            load_after  = post_vals.mean()
            load_change = load_after - load_before

    fig, axes = plt.subplots(4, 1, figsize=(13, 15), sharex=True, dpi=150)
    fig.patch.set_facecolor(_BG)

    direction = "▲" if load_change > 0 else "▼"
    _pct_str = (
        f"  ({load_change / rated_load_kw * 100:+.1f}% rated)"
        if rated_load_kw and rated_load_kw > 0 else ""
    )
    title_str = (
        f"Event: {event_ts.strftime('%H:%M:%S')}   |   "
        f"Load: {load_before:.0f} \u2192 {load_after:.0f} kW   "
        f"{direction} {abs(load_change):.0f} kW{_pct_str}"
    )
    fig.suptitle(title_str, fontsize=15, fontweight="700",
                 color=_TEXT_MAIN, y=0.995, x=0.01, ha="left")

    panel_cfg = [
        ("Voltage (L-L)", _BLUE),
        ("Current (A)",   _RED),
        ("Frequency (Hz)", _ORANGE),
        ("Power (kW)",    _GREEN),
    ]

    def _draw_panel(ax, x, y, label, color, multi=False):
        _style_ax(ax, label, color)
        if multi:
            return
        ax.fill_between(x, y, y.min(), color=color, alpha=0.1)
        ax.plot(x, y, color=color, linewidth=2.0, solid_capstyle="round")

    # 1. Voltage
    v_cols_ln = ["U1_rms_AVG", "U2_rms_AVG", "U3_rms_AVG"]
    v_cols_ll = ["U12_rms_AVG", "U23_rms_AVG", "U31_rms_AVG"]
    v_to_plot = [c for c in v_cols_ln if c in df_win.columns]
    scale = np.sqrt(3) if v_to_plot else 1.0
    if not v_to_plot:
        v_to_plot = [c for c in v_cols_ll if c in df_win.columns]
    use_avg = not v_to_plot and "U_avg_AVG" in df_win.columns

    _style_ax(axes[0], "Voltage (L-L)", _BLUE)
    phase_colors = [_BLUE, _RED, _GREEN]
    if use_avg:
        y = pd.to_numeric(df_win["U_avg_AVG"], errors="coerce")
        axes[0].fill_between(df_win["Timestamp"], y, y.min(), color=_BLUE, alpha=0.1)
        axes[0].plot(df_win["Timestamp"], y, color=_BLUE, linewidth=2.0,
                     solid_capstyle="round", label="V avg")
        axes[0].legend(loc="upper right", fontsize=10, framealpha=0.9,
                       edgecolor=_GRID, facecolor=_BG)
    else:
        for i, c in enumerate(v_to_plot):
            y = pd.to_numeric(df_win[c], errors="coerce") * scale
            axes[0].plot(df_win["Timestamp"], y,
                         label=c.split("_")[0], color=phase_colors[i % 3],
                         linewidth=2.0, solid_capstyle="round")
        if v_to_plot:
            axes[0].legend(loc="upper right", fontsize=10, framealpha=0.9,
                           edgecolor=_GRID, facecolor=_BG)
    if show_deviation_limits:
        lkw = dict(linewidth=1.5, linestyle="--", alpha=0.75, zorder=4)
        _snap_v_up = event_row.get("V_max_dev_upper_pct", v_max_dev) if event_row is not None else v_max_dev
        _snap_v_lo = event_row.get("V_max_dev_lower_pct", v_max_dev) if event_row is not None else v_max_dev
        if pd.isnull(_snap_v_up): _snap_v_up = v_max_dev
        if pd.isnull(_snap_v_lo): _snap_v_lo = v_max_dev
        # Load increase → voltage drops → only the lower limit is the applicable
        # threshold. Load decrease → voltage rises → only the upper limit applies.
        _v_dkw = event_row.get("dKw", 0) if event_row is not None else 0
        if _v_dkw <= 0:
            axes[0].axhline(nom_v * (1 + _snap_v_up / 100), color=_RED,
                            label=f"Max dev +{_snap_v_up}% ({nom_v * (1 + _snap_v_up / 100):.1f}V)", **lkw)
        else:
            axes[0].axhline(nom_v * (1 - _snap_v_lo / 100), color=_RED,
                            label=f"Max dev -{_snap_v_lo}% ({nom_v * (1 - _snap_v_lo / 100):.1f}V)", **lkw)
        axes[0].legend(loc="upper right", fontsize=10, framealpha=0.9,
                       edgecolor=_GRID, facecolor=_BG)

    # 2. Current
    i_cols = ["I1_rms_AVG", "I2_rms_AVG", "I3_rms_AVG"]
    _style_ax(axes[1], "Current (A)", _RED)
    for i, c in enumerate(i_cols):
        if c in df_win.columns:
            axes[1].plot(df_win["Timestamp"],
                         pd.to_numeric(df_win[c], errors="coerce"),
                         label=c.split("_")[0], color=phase_colors[i],
                         linewidth=2.0, solid_capstyle="round")
    if any(c in df_win.columns for c in i_cols):
        axes[1].legend(loc="upper right", fontsize=10, framealpha=0.9,
                       edgecolor=_GRID, facecolor=_BG)

    # 3. Frequency
    _style_ax(axes[2], "Frequency (Hz)", _ORANGE)
    if "Freq_AVG" in df_win.columns:
        y = pd.to_numeric(df_win["Freq_AVG"], errors="coerce")
        axes[2].fill_between(df_win["Timestamp"], y, y.min(), color=_ORANGE, alpha=0.1)
        axes[2].plot(df_win["Timestamp"], y,
                     color=_ORANGE, linewidth=2.0, solid_capstyle="round")
    if show_deviation_limits:
        lkw = dict(linewidth=1.5, linestyle="--", alpha=0.75, zorder=4)
        _snap_f_up = event_row.get("F_max_dev_upper_pct", f_max_dev) if event_row is not None else f_max_dev
        _snap_f_lo = event_row.get("F_max_dev_lower_pct", f_max_dev) if event_row is not None else f_max_dev
        if pd.isnull(_snap_f_up): _snap_f_up = f_max_dev
        if pd.isnull(_snap_f_lo): _snap_f_lo = f_max_dev
        # Load increase → freq drops → only the lower limit applies.
        # Load decrease → freq rises → only the upper limit applies.
        _f_dkw = event_row.get("dKw", 0) if event_row is not None else 0
        if _f_dkw <= 0:
            axes[2].axhline(nom_f * (1 + _snap_f_up / 100), color=_RED,
                            label=f"Max dev +{_snap_f_up}% ({nom_f * (1 + _snap_f_up / 100):.3f}Hz)", **lkw)
        else:
            axes[2].axhline(nom_f * (1 - _snap_f_lo / 100), color=_RED,
                            label=f"Max dev -{_snap_f_lo}% ({nom_f * (1 - _snap_f_lo / 100):.3f}Hz)", **lkw)
        axes[2].legend(loc="upper right", fontsize=10, framealpha=0.9,
                       edgecolor=_GRID, facecolor=_BG)

    # 4. Power
    _style_ax(axes[3], "Power (kW)", _GREEN)
    if "P_sum_AVG" in df_win.columns:
        y = pd.to_numeric(df_win["P_sum_AVG"], errors="coerce") / 1000
        axes[3].fill_between(df_win["Timestamp"], y, y.min(), color=_GREEN, alpha=0.1)
        axes[3].plot(df_win["Timestamp"], y,
                     color=_GREEN, linewidth=2.0, solid_capstyle="round")

    # ── Event detection overlay ───────────────────────────────────────────
    if show_debug and event_row is not None:
        ev_kw = dict(linewidth=1.0, linestyle=":", zorder=5, alpha=0.85)
        axes[0].axvline(event_ts, color=_AMBER, **ev_kw)
        axes[2].axvline(event_ts, color=_AMBER, **ev_kw)

    # ── Tolerance band + Intersection points overlay ─────────────────────
    if (show_tolerance_band or show_intersections or show_max_deviation) and event_row is not None:
        from matplotlib.lines import Line2D
        cross_kw = dict(linewidth=1.0, linestyle=":", zorder=5, alpha=0.85)
        lkw_dbg  = dict(lw=1.2, ls="--", alpha=0.85, zorder=4)

        v_upper_band = event_row.get("V_rec_upper", nom_v * (1 + tol_v / 100))
        v_lower_band = event_row.get("V_rec_lower", nom_v * (1 - tol_v / 100))
        if pd.isnull(v_upper_band): v_upper_band = nom_v * (1 + tol_v / 100)
        if pd.isnull(v_lower_band): v_lower_band = nom_v * (1 - tol_v / 100)

        v_dev   = event_row.get("V_dev",       np.nan)
        v_exit  = event_row.get("V_exit_ts")
        v_rec_s = event_row.get("V_rec_s")
        f_dev   = event_row.get("F_dev",       np.nan)
        f_exit  = event_row.get("F_exit_ts")
        f_rec_s = event_row.get("F_rec_s")
        f_upper = event_row.get("F_rec_upper", nom_f * (1 + tol_f / 100))
        f_lower = event_row.get("F_rec_lower", nom_f * (1 - tol_f / 100))
        if pd.isnull(f_upper): f_upper = nom_f * (1 + tol_f / 100)
        if pd.isnull(f_lower): f_lower = nom_f * (1 - tol_f / 100)

        # ── Voltage panel ────────────────────────────────────────────────
        if show_tolerance_band:
            axes[0].axhline(v_upper_band, color=_AMBER,
                            label=f"V limit +{tol_v}% ({v_upper_band:.1f} V)", **lkw_dbg)
            axes[0].axhline(v_lower_band, color=_AMBER,
                            label=f"V limit -{tol_v}% ({v_lower_band:.1f} V)", **lkw_dbg)

        v_band_val = v_upper_band if (pd.notnull(v_dev) and v_dev > nom_v) else v_lower_band

        if show_intersections and pd.notnull(v_exit):
            vx = pd.Timestamp(v_exit)
            axes[0].axvline(vx, color=_ORANGE, **cross_kw)
            axes[0].scatter([vx], [v_band_val], color=_ORANGE, marker="*", s=140, zorder=7)
            axes[0].annotate("exit", xy=(vx, v_band_val), xytext=(4, -14),
                             textcoords="offset points",
                             fontsize=7, color=_ORANGE, fontweight="700")
            if pd.notnull(v_rec_s):
                vr = vx + pd.Timedelta(seconds=float(v_rec_s))
                axes[0].axvline(vr, color=_LIME, **cross_kw)
                axes[0].scatter([vr], [v_band_val], color=_LIME, marker="*", s=140, zorder=7)
                axes[0].annotate(f"{v_rec_s:.2f}s", xy=(vr, v_band_val), xytext=(4, 6),
                                 textcoords="offset points",
                                 fontsize=7, color=_LIME, fontweight="700")

        # Max-deviation marker — red ★ at the actual extreme of the signal
        # within the post-event 5 s window (matches _measured_extreme()).
        v_dev_t = None
        f_dev_t = None
        if show_max_deviation:
            _dkw = event_row.get("dKw", 0) if event_row is not None else 0
            _v_nr = bool(event_row.get("V_not_recovered", False)) if event_row is not None else False
            _f_nr = bool(event_row.get("F_not_recovered", False)) if event_row is not None else False
            # For not-recovered events the deep dip is BEFORE event_ts (carry-over
            # from the prior step), so widen the marker-placement search to match
            # the widened V_dev/F_dev computation in analysis.py.
            _v_start = event_ts - pd.Timedelta(seconds=left_s) if _v_nr else event_ts
            _f_start = event_ts - pd.Timedelta(seconds=left_s) if _f_nr else event_ts
            _post_end = event_ts + pd.Timedelta(seconds=right_s)
            _v_post = df_win[
                (df_win["Timestamp"] >= _v_start) &
                (df_win["Timestamp"] <= _post_end)
            ]
            _f_post = df_win[
                (df_win["Timestamp"] >= _f_start) &
                (df_win["Timestamp"] <= _post_end)
            ]
            # Resolve a voltage column actually present in df_raw — Avg_Voltage_LL
            # only exists in df_proc, so we fall back to the columns the plot uses.
            _v_src_col = None
            for _c in ("U_avg_AVG", "U12_rms_AVG", "U23_rms_AVG", "U31_rms_AVG",
                       "U1_rms_AVG", "U2_rms_AVG", "U3_rms_AVG"):
                if _c in _v_post.columns:
                    _v_src_col = _c
                    break
            # Place the value label BELOW dips (load increase, dKw>0) and
            # ABOVE peaks (load decrease, dKw<=0) so it never sits on the line.
            _v_off = (4, -14) if _dkw > 0 else (4, 10)
            _f_off = (4, -14) if _dkw > 0 else (4, 10)
            if not _v_post.empty and pd.notnull(v_dev) and _v_src_col is not None:
                _vs = pd.to_numeric(_v_post[_v_src_col], errors="coerce")
                _vidx = _vs.idxmin() if _dkw > 0 else _vs.idxmax()
                if pd.notnull(_vidx):
                    v_dev_t = _v_post.loc[_vidx, "Timestamp"]
                    axes[0].scatter([v_dev_t], [v_dev], color=_RED, marker="*",
                                    s=160, zorder=8, edgecolor="white", linewidth=1.0)
                    axes[0].annotate(f"{v_dev:.1f} V", xy=(v_dev_t, v_dev), xytext=_v_off,
                                     textcoords="offset points",
                                     fontsize=7, color=_RED, fontweight="700")
            if not _f_post.empty and pd.notnull(f_dev) and "Freq_AVG" in _f_post.columns:
                _fs = pd.to_numeric(_f_post["Freq_AVG"], errors="coerce")
                _fidx = _fs.idxmin() if _dkw > 0 else _fs.idxmax()
                if pd.notnull(_fidx):
                    f_dev_t = _f_post.loc[_fidx, "Timestamp"]
                    axes[2].scatter([f_dev_t], [f_dev], color=_RED, marker="*",
                                    s=160, zorder=8, edgecolor="white", linewidth=1.0)
                    axes[2].annotate(f"{f_dev:.3f} Hz", xy=(f_dev_t, f_dev), xytext=_f_off,
                                     textcoords="offset points",
                                     fontsize=7, color=_RED, fontweight="700")

        _leg_v_up = event_row.get("V_max_dev_upper_pct", v_max_dev) if event_row is not None else v_max_dev
        _leg_v_lo = event_row.get("V_max_dev_lower_pct", v_max_dev) if event_row is not None else v_max_dev
        if pd.isnull(_leg_v_up): _leg_v_up = v_max_dev
        if pd.isnull(_leg_v_lo): _leg_v_lo = v_max_dev
        v_upper_dev = nom_v * (1 + _leg_v_up / 100)
        v_lower_dev = nom_v * (1 - _leg_v_lo / 100)

        v_legend = []
        if show_tolerance_band:
            v_legend.extend([
                Line2D([0], [0], color=_AMBER,  ls="--",   lw=1.5,      label=f"Tolerance +{tol_v}% ({v_upper_band:.1f} V)"),
                Line2D([0], [0], color=_AMBER,  ls="--",   lw=1.5,      label=f"Tolerance -{tol_v}% ({v_lower_band:.1f} V)"),
            ])
        if show_deviation_limits:
            _v_dkw_leg = event_row.get("dKw", 0) if event_row is not None else 0
            if _v_dkw_leg <= 0:
                v_legend.append(
                    Line2D([0], [0], color=_RED, ls="--", lw=1.5, label=f"Max Dev +{_leg_v_up}% ({v_upper_dev:.1f} V)")
                )
            else:
                v_legend.append(
                    Line2D([0], [0], color=_RED, ls="--", lw=1.5, label=f"Max Dev -{_leg_v_lo}% ({v_lower_dev:.1f} V)")
                )
        if show_intersections:
            _v_exit_lbl = "exit"
            _v_rec_lbl = "recovery"
            if pd.notnull(v_exit):
                _vx = pd.Timestamp(v_exit)
                _v_exit_lbl = f"exit ({_vx.strftime('%H:%M:%S.%f')[:-4]})"
                if pd.notnull(v_rec_s):
                    _vr = _vx + pd.Timedelta(seconds=float(v_rec_s))
                    _v_rec_lbl = f"recovery (+{float(v_rec_s):.2f}s @ {_vr.strftime('%H:%M:%S.%f')[:-4]})"
            v_legend.extend([
                Line2D([0], [0], color=_ORANGE, marker="*", ls="none",  markersize=10, label=_v_exit_lbl),
                Line2D([0], [0], color=_LIME,   marker="*", ls="none",  markersize=10, label=_v_rec_lbl),
            ])
        if show_max_deviation and pd.notnull(v_dev):
            _v_pct = (v_dev - nom_v) / nom_v * 100 if nom_v else 0
            v_legend.append(
                Line2D([0], [0], color=_RED, marker="*", ls="none", markersize=11,
                       markeredgecolor="white", markeredgewidth=1.0,
                       label=f"Max Deviation ({v_dev:.1f} V, {_v_pct:+.2f}%)")
            )
        def _pick_legend_loc(exit_ts, rec_s):
            """Flip to upper-left if any marker sits in the right 30% of the window."""
            if pd.isnull(exit_ts):
                return "upper right"
            threshold = event_ts + pd.Timedelta(seconds=right_s * 0.4)
            ex = pd.Timestamp(exit_ts)
            if ex >= threshold:
                return "upper left"
            if pd.notnull(rec_s):
                if ex + pd.Timedelta(seconds=float(rec_s)) >= threshold:
                    return "upper left"
            return "upper right"

        if v_legend:
            axes[0].legend(handles=v_legend, fontsize=8, framealpha=0.9,
                           loc=_pick_legend_loc(v_exit, v_rec_s),
                           edgecolor=_GRID, facecolor=_BG)

        # ── Frequency panel ──────────────────────────────────────────────
        if show_tolerance_band:
            axes[2].axhline(f_upper, color=_AMBER,
                            label=f"F limit upper ({f_upper:.3f} Hz)", **lkw_dbg)
            axes[2].axhline(f_lower, color=_AMBER,
                            label=f"F limit lower ({f_lower:.3f} Hz)", **lkw_dbg)

        f_band_val = f_upper if (pd.notnull(f_dev) and f_dev > nom_f) else f_lower

        if show_intersections and pd.notnull(f_exit):
            fx = pd.Timestamp(f_exit)
            axes[2].axvline(fx, color=_ORANGE, **cross_kw)
            axes[2].scatter([fx], [f_band_val], color=_ORANGE, marker="*", s=140, zorder=7)
            axes[2].annotate("exit", xy=(fx, f_band_val), xytext=(4, -14),
                             textcoords="offset points",
                             fontsize=7, color=_ORANGE, fontweight="700")
            if pd.notnull(f_rec_s):
                fr = fx + pd.Timedelta(seconds=float(f_rec_s))
                axes[2].axvline(fr, color=_LIME, **cross_kw)
                axes[2].scatter([fr], [f_band_val], color=_LIME, marker="*", s=140, zorder=7)
                axes[2].annotate(f"{f_rec_s:.2f}s", xy=(fr, f_band_val), xytext=(4, 6),
                                 textcoords="offset points",
                                 fontsize=7, color=_LIME, fontweight="700")

        _leg_f_up = event_row.get("F_max_dev_upper_pct", f_max_dev) if event_row is not None else f_max_dev
        _leg_f_lo = event_row.get("F_max_dev_lower_pct", f_max_dev) if event_row is not None else f_max_dev
        if pd.isnull(_leg_f_up): _leg_f_up = f_max_dev
        if pd.isnull(_leg_f_lo): _leg_f_lo = f_max_dev
        f_upper_dev = nom_f * (1 + _leg_f_up / 100)
        f_lower_dev = nom_f * (1 - _leg_f_lo / 100)

        f_legend = []
        if show_tolerance_band:
            f_legend.extend([
                Line2D([0], [0], color=_AMBER,  ls="--",   lw=1.5,      label=f"Recovery upper ({f_upper:.3f} Hz)"),
                Line2D([0], [0], color=_AMBER,  ls="--",   lw=1.5,      label=f"Recovery lower ({f_lower:.3f} Hz)"),
            ])
        if show_deviation_limits:
            _f_dkw_leg = event_row.get("dKw", 0) if event_row is not None else 0
            if _f_dkw_leg <= 0:
                f_legend.append(
                    Line2D([0], [0], color=_RED, ls="--", lw=1.5, label=f"Max Dev +{_leg_f_up}% ({f_upper_dev:.3f} Hz)")
                )
            else:
                f_legend.append(
                    Line2D([0], [0], color=_RED, ls="--", lw=1.5, label=f"Max Dev -{_leg_f_lo}% ({f_lower_dev:.3f} Hz)")
                )
        if show_intersections:
            _f_exit_lbl = "exit"
            _f_rec_lbl = "recovery"
            if pd.notnull(f_exit):
                _fx = pd.Timestamp(f_exit)
                _f_exit_lbl = f"exit ({_fx.strftime('%H:%M:%S.%f')[:-4]})"
                if pd.notnull(f_rec_s):
                    _fr = _fx + pd.Timedelta(seconds=float(f_rec_s))
                    _f_rec_lbl = f"recovery (+{float(f_rec_s):.2f}s @ {_fr.strftime('%H:%M:%S.%f')[:-4]})"
            f_legend.extend([
                Line2D([0], [0], color=_ORANGE, marker="*", ls="none",  markersize=10, label=_f_exit_lbl),
                Line2D([0], [0], color=_LIME,   marker="*", ls="none",  markersize=10, label=_f_rec_lbl),
            ])
        if show_max_deviation and pd.notnull(f_dev):
            _f_pct = (f_dev - nom_f) / nom_f * 100 if nom_f else 0
            f_legend.append(
                Line2D([0], [0], color=_RED, marker="*", ls="none", markersize=11,
                       markeredgecolor="white", markeredgewidth=1.0,
                       label=f"Max Deviation ({f_dev:.3f} Hz, {_f_pct:+.2f}%)")
            )
        if f_legend:
            axes[2].legend(handles=f_legend, fontsize=8, framealpha=0.9,
                           loc=_pick_legend_loc(f_exit, f_rec_s),
                           edgecolor=_GRID, facecolor=_BG)

    x_left = event_ts - pd.Timedelta(seconds=left_s)
    x_right = event_ts + pd.Timedelta(seconds=right_s)
    for ax in axes:
        ax.set_xlim(x_left, x_right)
        ax.xaxis.set_major_locator(mdates.SecondLocator(interval=1))
    axes[3].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.autofmt_xdate(rotation=0, ha="center")
    axes[3].tick_params(axis="x", labelsize=11, colors=_TEXT_SUB)

    # ── Not-recovered highlighting ──────────────────────────────────────
    if event_row is not None:
        v_nr = bool(event_row.get("V_not_recovered", False))
        f_nr = bool(event_row.get("F_not_recovered", False))
        if v_nr:
            axes[0].set_facecolor("#fef2f2")  # light red tint
            axes[0].text(
                0.5, 0.5, "VOLTAGE NOT RECOVERED FROM PREVIOUS STEP",
                transform=axes[0].transAxes, fontsize=10, fontweight="700",
                color="#dc2626", alpha=0.35, ha="center", va="center",
                zorder=1,
            )
        if f_nr:
            axes[2].set_facecolor("#fef2f2")
            axes[2].text(
                0.5, 0.5, "FREQUENCY NOT RECOVERED FROM PREVIOUS STEP",
                transform=axes[2].transAxes, fontsize=10, fontweight="700",
                color="#dc2626", alpha=0.35, ha="center", va="center",
                zorder=1,
            )

    # Panel corner labels — use metric color for visual identification
    _panel_labels = [
        ("V", _BLUE), ("I", _RED), ("f", _ORANGE), ("P", _GREEN),
    ]
    for ax, (lbl, lbl_color) in zip(axes, _panel_labels):
        ax.text(0.005, 0.92, lbl, transform=ax.transAxes,
                fontsize=11, fontweight="700", color=lbl_color,
                alpha=0.6, va="top", ha="left")

    fig.tight_layout(rect=[0, 0, 1, 0.995], h_pad=0.6)

    fname = os.path.join(output_dir, f"snap_{client_name}_{event_ts.strftime('%Y%m%d_%H%M%S')}.jpeg")
    fig.savefig(fname, dpi=150, facecolor=_BG)
    plt.close(fig)
    return fname


def generate_all_snapshots(df_raw, df_events, client_name, output_dir="output/Snapshots",
                           show_limits=False, show_tolerance_band=True, show_deviation_limits=True,
                           nom_v=415.0, nom_f=50.0, tol_v=1.0, tol_f=0.5,
                           v_max_dev=15.0, f_max_dev=7.0,
                           show_debug=False, show_intersections=False,
                           show_max_deviation=False, rated_load_kw=None,
                           window_s=10,
                           window_overrides=None, offset_overrides=None):
    """Generate snapshots for all detected events. Returns (list of file paths, list of errors).

    window_overrides / offset_overrides are optional dicts keyed by df_events
    integer index, carrying the per-snapshot window size and time-shift the user
    set in the event expander UI. When provided, they take priority over the
    global window_s and the default 0 s offset for that specific event.
    """
    import logging
    log = logging.getLogger(__name__)

    if df_events.empty:
        return [], []

    window_overrides = window_overrides or {}
    offset_overrides = offset_overrides or {}

    paths = []
    snapshot_errors = []
    _events_seq = list(df_events.iterrows())
    for idx, (ev_idx, row) in enumerate(_events_seq):
        try:
            _prev_ts = _events_seq[idx - 1][1]["Timestamp"] if idx > 0 else None
            _next_ts = _events_seq[idx + 1][1]["Timestamp"] if idx + 1 < len(_events_seq) else None
            _win = float(window_overrides.get(ev_idx, window_s))
            _off = float(offset_overrides.get(ev_idx, 0.0))
            path = plot_load_change_snapshot(
                df_raw,
                event_ts=row["Timestamp"],
                load_change=row["dKw"],
                load_before=row["Avg_kW"] - row["dKw"],
                load_after=row["Avg_kW"],
                client_name=client_name,
                output_dir=output_dir,
                show_limits=show_limits,
                show_tolerance_band=show_tolerance_band,
                show_deviation_limits=show_deviation_limits,
                nom_v=nom_v, nom_f=nom_f, tol_v=tol_v, tol_f=tol_f,
                v_max_dev=v_max_dev, f_max_dev=f_max_dev,
                show_debug=show_debug,
                show_intersections=show_intersections,
                event_row=row,
                show_max_deviation=show_max_deviation,
                rated_load_kw=rated_load_kw,
                window_s=_win,
                time_offset_s=_off,
                prev_event_ts=_prev_ts,
                next_event_ts=_next_ts,
            )
            paths.append(path)
        except Exception as e:
            log.exception("Snapshot generation failed for event at %s", row["Timestamp"])
            snapshot_errors.append(f"❌ Event #{idx+1} ({row['Timestamp'].strftime('%H:%M:%S')}): {str(e)}")
            paths.append(None)
    return paths, snapshot_errors


def save_compliance_table_as_image(df, filename, title_text, nom_v=415.0, nom_f=50.0, rated_load_kw=None):
    """
    Render the compliance DataFrame as a styled JPEG table image.

    Returns:
        str: path to saved image
    """
    if df.empty:
        return None

    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)

    import textwrap

    def _wrap(text, width):
        s = str(text).strip()
        if not s or s == "nan":
            return "—"
        return "\n".join(textwrap.wrap(s, width=width))

    # Drop Failure Reasons column when every event passed — it only adds noise.
    has_failures = (
        "Failure_Reasons" in df.columns
        and df["Failure_Reasons"].astype(str).str.strip().replace("nan", "").ne("").any()
    )
    display_cols = [
        "Timestamp", "dKw", "V_dev", "V_rec_s", "F_dev", "F_rec_s",
        "Compliance_Status",
    ]
    if has_failures:
        display_cols.append("Failure_Reasons")
    avail_cols = [c for c in display_cols if c in df.columns]
    plot_data = df[avail_cols].copy()

    def format_range(row):
        s = row["Timestamp"]
        e = row.get("End_Timestamp", s)
        if pd.isna(e) or s == e:
            return s.strftime("%H:%M:%S")
        return s.strftime("%H:%M:") + f"{s.strftime('%S')}-{e.strftime('%S')}"

    plot_data["Timestamp"] = df.apply(format_range, axis=1)
    if "dKw" in plot_data.columns:
        dkw_num = pd.to_numeric(plot_data["dKw"], errors="coerce")
        def _fmt_dkw(x):
            if pd.isnull(x):
                return "—"
            kw_str = f"{x:+,.1f} kW"
            if rated_load_kw and rated_load_kw > 0:
                pct = x / rated_load_kw * 100
                return f"{kw_str}\n({pct:+.1f}% rated)"
            return kw_str
        plot_data["dKw"] = dkw_num.map(_fmt_dkw)

    # Voltage Deviation — actual measured min/max voltage (V)
    if "V_dev" in plot_data.columns:
        v_dev_raw = pd.to_numeric(df["V_dev"], errors="coerce")
        plot_data["V_dev"] = v_dev_raw.apply(
            lambda x: f"{x:.1f} V\n({(x - nom_v) / nom_v * 100:+.2f}%)" if pd.notnull(x) else "—"
        )

    # Frequency Deviation — actual measured min/max frequency (Hz)
    if "F_dev" in plot_data.columns:
        f_dev_raw = pd.to_numeric(df["F_dev"], errors="coerce")
        plot_data["F_dev"] = f_dev_raw.apply(
            lambda x: f"{x:.3f} Hz\n({(x - nom_f) / nom_f * 100:+.2f}%)" if pd.notnull(x) else "—"
        )

    if "V_rec_s" in plot_data.columns:
        plot_data["V_rec_s"] = pd.to_numeric(plot_data["V_rec_s"]).map(
            lambda x: f"{x:.2f} s" if pd.notnull(x) else "—")
    if "F_rec_s" in plot_data.columns:
        plot_data["F_rec_s"] = pd.to_numeric(plot_data["F_rec_s"]).map(
            lambda x: f"{x:.2f} s" if pd.notnull(x) else "—")
    if "Failure_Reasons" in plot_data.columns:
        plot_data["Failure_Reasons"] = plot_data["Failure_Reasons"].apply(
            lambda x: _wrap(x, width=38))

    rename_map = {
        "Timestamp":          "Event Time",
        "dKw":                "Load Change",
        "V_dev":              "Voltage Deviation",
        "F_dev":              "Frequency Deviation",
        "V_rec_s":            "Voltage Recovery",
        "F_rec_s":            "Frequency Recovery",
        "Compliance_Status":  "Compliance Status",
        "Failure_Reasons":    "Failure Reasons",
    }
    plot_data.columns = [rename_map.get(c, c) for c in plot_data.columns]

    n_cols = len(plot_data.columns)

    # Per-row line counts drive individual row heights.
    base_row_h = 0.72
    extra_per_line = 0.38
    header_h_in = 0.60
    row_line_counts = []
    for _, row in plot_data.iterrows():
        max_lines = max(str(v).count("\n") + 1 for v in row)
        row_line_counts.append(max_lines)

    total_data_h = sum(base_row_h + extra_per_line * (lc - 1) for lc in row_line_counts)
    fig_h = max(4.0, total_data_h + header_h_in + 1.0)
    fig_w = 22

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)
    ax.axis("off")

    tbl = ax.table(
        cellText=plot_data.values,
        colLabels=plot_data.columns,
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)

    # Per-row heights in figure-fraction units.
    for col_idx in range(n_cols):
        tbl[0, col_idx].set_height(header_h_in / fig_h)
    for row_idx, lc in enumerate(row_line_counts, start=1):
        rh = (base_row_h + extra_per_line * (lc - 1)) / fig_h
        for col_idx in range(n_cols):
            tbl[row_idx, col_idx].set_height(rh)

    # Column index lookups for conditional styling.
    cols = list(plot_data.columns)
    status_idx  = next((i for i, c in enumerate(cols) if c == "Compliance Status"), -1)
    notes_idx   = next((i for i, c in enumerate(cols) if c == "Failure Reasons"),   -1)
    numeric_idx = {i for i, c in enumerate(cols)
                   if c in ("Load Change", "Voltage Deviation", "Frequency Deviation",
                             "Voltage Recovery", "Frequency Recovery")}

    # Palette
    _HDR_BG   = _NAVY
    _HDR_FG   = "#ffffff"
    _ROW_ODD  = "#ffffff"
    _ROW_EVEN = "#f0f4f8"
    _ACCENT   = "#2563eb"
    _PASS_BG  = "#dcfce7"
    _FAIL_BG  = "#fee2e2"
    _BORDER   = "#cbd5e1"

    for (row, col), cell in tbl.get_celld().items():
        cell.set_linewidth(0)          # remove default borders; we'll draw selectively
        cell.PAD = 0.10

        if row == 0:
            # Header
            cell.set_facecolor(_HDR_BG)
            cell.set_text_props(color=_HDR_FG, weight="bold", fontsize=20)
            cell.set_edgecolor(_ACCENT)
            cell.set_linewidth(1.5)
        else:
            is_even = (row % 2 == 0)
            cell.set_facecolor(_ROW_EVEN if is_even else _ROW_ODD)
            cell.set_edgecolor(_BORDER)
            cell.set_linewidth(0.4)
            cell.set_text_props(fontsize=20, color=_TEXT_MAIN)

            # Numeric / data columns: slightly muted colour
            if col in numeric_idx:
                cell.set_text_props(fontsize=20, color=_TEXT_SUB)

            # Compliance Status — coloured badge background
            if col == status_idx:
                val = str(plot_data.iloc[row - 1, status_idx])
                is_pass = "Pass" in val
                cell.set_facecolor(_PASS_BG if is_pass else _FAIL_BG)
                cell.set_text_props(
                    fontsize=21, weight="bold",
                    color=_GREEN if is_pass else _RED,
                )

            # Failure Reasons — left-aligned for readability
            if col == notes_idx:
                cell.set_text_props(fontsize=18, color="#64748b", ha="left")

    # Title block
    fig.text(0.5, 0.995, "ISO 8528 Compliance Report", ha="center", va="top",
             fontsize=25, fontweight="800", color=_TEXT_MAIN)

    fig.tight_layout(rect=[0.005, 0.005, 0.995, 0.955])
    svg_path = os.path.splitext(filename)[0] + ".svg"
    fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor=_BG)
    # Also save a PNG for Word/PDF report insertion (SVG cannot be embedded in docx).
    png_path = os.path.splitext(filename)[0] + ".png"
    fig.savefig(png_path, format="png", dpi=250, bbox_inches="tight", facecolor=_BG)
    plt.close(fig)
    return svg_path


# ── ECU Plotting ────────────────────────────────────────────────────────────
_ECU_PALETTE = (_BLUE, _GREEN, _RED, _ORANGE, _CYAN, _PURPLE, _AMBER, _LIME)


def plot_ecu_group(df, columns, title, output_dir, filename, label_map=None):
    """
    Render a multi-channel ECU time-series plot.

    Parameters:
        df: DataFrame with a "Timestamp" column + numeric channel columns.
        columns: list of channel names from df to overlay on a single axis.
        title: plot title (group name shown to the user).
        output_dir: directory to write the PNG.
        filename: filename (basename) for the saved PNG.
        label_map: optional {raw_column_name: display_label} for nicer legend
                   text. Falls back to the raw name when unmapped.

    Returns:
        Path to the saved PNG, or None if `columns` is empty.

    Notes:
        Channels are drawn in order using a deterministic colour palette
        that cycles for >8 channels. Single shared y-axis — channels with
        mismatched units should be moved to separate groups by the user
        rather than auto-normalised.
    """
    if not columns:
        return None

    os.makedirs(output_dir, exist_ok=True)
    label_map = label_map or {}

    fig, ax = plt.subplots(figsize=(14, 5))
    fig.patch.set_facecolor(_BG)

    x = df["Timestamp"]
    for i, col in enumerate(columns):
        if col not in df.columns:
            continue
        y = df[col]
        ax.plot(x, y, color=_ECU_PALETTE[i % len(_ECU_PALETTE)],
                linewidth=1.6, solid_capstyle="round",
                label=label_map.get(col, col))

    _style_ax(ax, "Value", _TEXT_MAIN)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.autofmt_xdate(rotation=0, ha="center")
    ax.tick_params(axis="x", labelsize=11, colors=_TEXT_SUB)
    ax.legend(fontsize=10, framealpha=0.9, loc="upper right",
              edgecolor=_GRID, ncol=min(3, max(1, len(columns) // 4 + 1)))

    ax.set_title(title, fontsize=16, fontweight="700",
                 color=_TEXT_MAIN, pad=18, loc="left")

    fig.tight_layout(pad=1.2)
    out_path = os.path.join(output_dir, filename)
    fig.savefig(out_path, format="png", dpi=130, bbox_inches="tight", facecolor=_BG)
    plt.close(fig)
    return out_path
