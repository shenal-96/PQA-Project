"""Side-by-side diff viewer for ECU parameter files.

Renders an HTML page (intended for ``st.components.v1.html``) showing the full
parsed document with cells tinted where values differ between files, alongside
a change navigator panel that scrolls the table to each diff when clicked.

No Streamlit imports — keep this UI-free so it can be unit-tested.

Two builders are exported:

* :func:`build_csv_view`  — flat CSV (ComAp config) files.
* :func:`build_xls_view`  — multi-sheet ECU parameter files (XLS / XLSX).

Both return ``(html: str, diff_count: int)``.
"""

from __future__ import annotations

import html
from typing import Any, Iterable

# ── Comparison helpers ────────────────────────────────────────────────────────

def _norm(v: Any, *, ignore_whitespace: bool, ignore_case: bool) -> str:
    """Normalise a cell value to a string for equality comparison."""
    if v is None:
        return ""
    try:
        # Treat NaN as empty
        if isinstance(v, float) and v != v:  # noqa: PLR0124 — NaN check
            return ""
    except Exception:
        pass
    s = str(v)
    if ignore_whitespace:
        s = "".join(s.split())
    else:
        s = s.strip()
    if ignore_case:
        s = s.lower()
    return s


def _fmt_cell(v: Any) -> str:
    """Format a cell value for display (preserves precision, blanks NaN)."""
    if v is None:
        return ""
    try:
        if isinstance(v, float) and v != v:  # NaN
            return ""
    except Exception:
        pass
    if isinstance(v, float):
        # Trim pointless trailing zeros while keeping meaningful precision
        if v.is_integer():
            return str(int(v))
        return f"{v:g}"
    return str(v)


def _row_has_diff(values_by_label: dict[str, Any], file_labels: list[str],
                  *, ignore_whitespace: bool, ignore_case: bool) -> bool:
    seen = set()
    for lbl in file_labels:
        n = _norm(values_by_label.get(lbl), ignore_whitespace=ignore_whitespace,
                  ignore_case=ignore_case)
        seen.add(n)
        if len(seen) > 1:
            return True
    return False


# ── HTML page wrapper ─────────────────────────────────────────────────────────

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
* { box-sizing: border-box; }
html, body { margin:0; padding:0; height:100%; background:#f8fafc;
  font-family:'Inter', -apple-system, sans-serif; color:#0f172a; font-size:13px; }
.diff-wrap { display:grid; grid-template-columns: 1fr 320px; height:100vh; gap:0; }
.diff-main { overflow:auto; background:#fff; }
.diff-side { background:#f1f5f9; border-left:1px solid #e2e8f0; overflow-y:auto;
  display:flex; flex-direction:column; }
.diff-side-head { position:sticky; top:0; background:#0f172a; color:#fff;
  padding:14px 16px; z-index:10; border-bottom:1px solid #1e293b; }
.diff-side-head .title { font-size:13px; font-weight:700; letter-spacing:0.04em;
  text-transform:uppercase; color:#fff; margin:0; }
.diff-side-head .count { font-size:11px; color:#94a3b8; margin-top:2px; }
.diff-side-list { padding:8px 10px 60px; }
.diff-side-empty { padding:24px 16px; color:#64748b; font-size:12px; text-align:center; }
.diff-card { display:block; background:#fff; border:1px solid #e2e8f0;
  border-left:3px solid #f59e0b; border-radius:8px; padding:8px 10px;
  margin-bottom:6px; cursor:pointer; text-decoration:none; color:inherit;
  transition: box-shadow 0.12s ease, transform 0.12s ease; }
.diff-card:hover { box-shadow:0 2px 8px rgba(15,23,42,0.08); transform:translateX(-1px); }
.diff-card .ref { font-size:10.5px; font-weight:700; color:#b45309;
  letter-spacing:0.06em; text-transform:uppercase; }
.diff-card .ctx { font-size:11.5px; color:#334155; margin:2px 0 4px;
  font-weight:600; line-height:1.3; word-break:break-word; }
.diff-card .vals { display:flex; flex-direction:column; gap:2px; margin-top:4px; }
.diff-card .val { font-family:'JetBrains Mono', monospace; font-size:11px;
  display:flex; gap:6px; align-items:flex-start; }
.diff-card .val .lbl { color:#64748b; min-width:0; max-width:120px;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.diff-card .val .v   { color:#0f172a; font-weight:600; word-break:break-all; }
.diff-card .val.is-a .v { color:#b91c1c; }
.diff-card .val.is-b .v { color:#047857; }

.section-header { background:#f8fafc; padding:14px 18px; border-bottom:1px solid #e2e8f0;
  position:sticky; top:0; z-index:5; }
.section-header h3 { margin:0; font-size:13px; font-weight:700; color:#0f172a;
  letter-spacing:0.04em; text-transform:uppercase; }
.section-header .sub { font-size:11px; color:#64748b; margin-top:2px; }

table.cmp { width:100%; border-collapse:separate; border-spacing:0;
  font-size:12.5px; }
table.cmp th { position:sticky; top:0; background:#f1f5f9; color:#374151;
  font-weight:700; padding:9px 12px; text-align:left; font-size:10.5px;
  letter-spacing:0.06em; text-transform:uppercase; border-bottom:2px solid #e2e8f0;
  white-space:nowrap; z-index:3; }
table.cmp th.file-col { background:#0f172a; color:#fff; }
table.cmp td { padding:7px 12px; border-bottom:1px solid #f1f5f9;
  vertical-align:top; line-height:1.45; }
table.cmp td.idcol { color:#64748b; font-family:'JetBrains Mono', monospace;
  font-size:11px; white-space:nowrap; }
table.cmp td.namecol { font-weight:600; color:#0f172a; max-width:340px; }
table.cmp td.valcol { font-family:'JetBrains Mono', monospace; font-size:12px;
  white-space:nowrap; }
table.cmp tr.diff-row td { background:#fffbeb; }
table.cmp tr.diff-row.target { animation: flash 1.2s ease-out; }
@keyframes flash {
  0%   { background:#fde68a; }
  100% { background:#fffbeb; }
}
table.cmp td.diff-cell-a { background:#fee2e2 !important; color:#991b1b; font-weight:700; }
table.cmp td.diff-cell-b { background:#d1fae5 !important; color:#065f46; font-weight:700; }
table.cmp td.diff-cell   { background:#fef3c7 !important; color:#92400e; font-weight:700; }
table.cmp tr:hover td { background:#f8fafc; }
table.cmp tr.diff-row:hover td { background:#fef3c7; }

.legend { padding:10px 18px; font-size:11px; color:#64748b;
  display:flex; gap:14px; flex-wrap:wrap; align-items:center;
  border-bottom:1px solid #e2e8f0; background:#fff; }
.legend .chip { display:inline-flex; align-items:center; gap:5px; }
.legend .sw { width:12px; height:12px; border-radius:3px; border:1px solid #e2e8f0; }
.empty-state { padding:60px 24px; text-align:center; color:#64748b; }
"""

_JS = """
// Smooth-scroll & flash the target row when a change card is clicked
document.addEventListener('click', function(e) {
  var a = e.target.closest('a.diff-card');
  if (!a) return;
  e.preventDefault();
  var id = a.getAttribute('href').replace('#', '');
  var row = document.getElementById(id);
  if (!row) return;
  // Clear previous target highlight
  document.querySelectorAll('tr.target').forEach(function(r){ r.classList.remove('target'); });
  row.classList.add('target');
  row.scrollIntoView({ behavior: 'smooth', block: 'center' });
});
"""


def _page(body: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{_CSS}</style></head>
<body><div class="diff-wrap">{body}</div><script>{_JS}</script></body></html>"""


def _change_card(anchor: str, ref: str, ctx: str,
                 values: list[tuple[str, str]],
                 two_file_mode: bool) -> str:
    """Build one change-navigator card. ``values`` is [(label, formatted_value), ...]."""
    rows = []
    for i, (lbl, v) in enumerate(values):
        cls = ""
        if two_file_mode and len(values) == 2:
            cls = "is-a" if i == 0 else "is-b"
        rows.append(
            f'<div class="val {cls}"><span class="lbl">{html.escape(lbl)}</span>'
            f'<span class="v">{html.escape(v) if v else "—"}</span></div>'
        )
    return (
        f'<a class="diff-card" href="#{html.escape(anchor)}">'
        f'<div class="ref">{html.escape(ref)}</div>'
        f'<div class="ctx">{html.escape(ctx)}</div>'
        f'<div class="vals">{"".join(rows)}</div>'
        '</a>'
    )


def _legend() -> str:
    return (
        '<div class="legend">'
        '<span class="chip"><span class="sw" style="background:#fffbeb;border-color:#fde68a;"></span>Row with differences</span>'
        '<span class="chip"><span class="sw" style="background:#fee2e2;border-color:#fca5a5;"></span>Baseline value</span>'
        '<span class="chip"><span class="sw" style="background:#d1fae5;border-color:#86efac;"></span>Comparison value</span>'
        '<span class="chip"><span class="sw" style="background:#fef3c7;border-color:#fde68a;"></span>Differing (3+ files)</span>'
        '</div>'
    )


def _side_panel(diff_count: int, cards_html: str) -> str:
    if diff_count == 0:
        body = '<div class="diff-side-empty">No differences — all files match.</div>'
    else:
        body = f'<div class="diff-side-list">{cards_html}</div>'
    return (
        '<aside class="diff-side">'
        '<div class="diff-side-head">'
        '<p class="title">Changes</p>'
        f'<div class="count">{diff_count} difference{"" if diff_count == 1 else "s"} found</div>'
        '</div>'
        f'{body}'
        '</aside>'
    )


# ── Row rendering ─────────────────────────────────────────────────────────────

def _render_table(
    columns_meta: list[dict],  # [{key, label, kind: id|name|value, file_label?}]
    rows: list[dict],          # each row: {id, anchor, has_diff, values: {col_key: raw_val}}
    file_labels: list[str],
    two_file_mode: bool,
) -> str:
    head = []
    for col in columns_meta:
        cls = "file-col" if col["kind"] == "value" else ""
        head.append(f'<th class="{cls}">{html.escape(col["label"])}</th>')
    head_html = f'<thead><tr>{"".join(head)}</tr></thead>'

    body = []
    for row in rows:
        tr_cls = "diff-row" if row.get("has_diff") else ""
        anchor = row.get("anchor", "")
        tds = []
        for col in columns_meta:
            raw = row["values"].get(col["key"])
            disp = html.escape(_fmt_cell(raw))
            if col["kind"] == "id":
                tds.append(f'<td class="idcol">{disp}</td>')
            elif col["kind"] == "name":
                tds.append(f'<td class="namecol">{disp}</td>')
            elif col["kind"] == "value":
                cell_cls = "valcol"
                if row.get("has_diff"):
                    if two_file_mode and len(file_labels) == 2:
                        idx = file_labels.index(col["file_label"])
                        cell_cls += " diff-cell-a" if idx == 0 else " diff-cell-b"
                    else:
                        cell_cls += " diff-cell"
                tds.append(f'<td class="{cell_cls}">{disp}</td>')
            else:
                tds.append(f'<td>{disp}</td>')
        body.append(
            f'<tr id="{html.escape(anchor)}" class="{tr_cls}">{"".join(tds)}</tr>'
        )
    body_html = f'<tbody>{"".join(body)}</tbody>'
    return f'<table class="cmp">{head_html}{body_html}</table>'


# ── CSV (ComAp config) builder ────────────────────────────────────────────────

def build_csv_view(
    csv_data: dict[str, dict],
    *,
    ignore_whitespace: bool = False,
    ignore_case: bool = False,
    hide_unchanged: bool = False,
    two_file_mode: bool = False,
    baseline: str | None = None,
    comparison: str | None = None,
    group_filter: Iterable[str] | None = None,
) -> tuple[str, int]:
    """Build the side-by-side HTML view for parsed ComAp CSV files.

    ``csv_data`` is ``{label: parse_csv_file(...)}``.
    """
    # Select which files participate
    if two_file_mode and baseline and comparison and baseline in csv_data and comparison in csv_data:
        file_labels = [baseline, comparison]
    else:
        file_labels = [lbl for lbl in csv_data if csv_data[lbl].get("type") == "csv"]
        two_file_mode = False

    if len(file_labels) < 2:
        return _page('<div class="diff-main"><div class="empty-state">'
                     'Need at least 2 files to compare.</div></div>'
                     + _side_panel(0, "")), 0

    # Union of keys (so rows missing in one file still appear, with empty cell)
    all_keys: set[str] = set()
    for lbl in file_labels:
        all_keys.update(csv_data[lbl].get("data", {}).keys())

    # Per-key metadata snapshot (first non-empty wins)
    rows_raw: list[dict] = []
    for key in all_keys:
        group = sub_group = name = dim = ""
        values: dict[str, Any] = {}
        for lbl in file_labels:
            param = csv_data[lbl].get("data", {}).get(key, {})
            values[lbl] = param.get("value", "")
            if not group:
                group = param.get("group", "")
            if not sub_group:
                sub_group = param.get("sub_group", "")
            if not name:
                name = param.get("name", "")
            if not dim:
                dim = param.get("dimension", "")
        rows_raw.append({
            "group": group, "sub_group": sub_group, "name": name, "dim": dim,
            "values": values, "key": key,
        })

    # Sort by group / sub-group / name to mirror file ordering
    rows_raw.sort(key=lambda r: (r["group"] or "", r["sub_group"] or "", r["name"] or ""))

    # Optional group filter
    if group_filter is not None:
        gf = set(group_filter)
        rows_raw = [r for r in rows_raw if r["group"] in gf]

    columns_meta: list[dict] = [
        {"key": "_group", "label": "Group", "kind": "id"},
        {"key": "_sub",   "label": "Sub-group", "kind": "id"},
        {"key": "_name",  "label": "Name", "kind": "name"},
        {"key": "_dim",   "label": "Dim.", "kind": "id"},
    ]
    for lbl in file_labels:
        columns_meta.append({
            "key": f"f::{lbl}", "label": lbl, "kind": "value", "file_label": lbl,
        })

    display_rows: list[dict] = []
    diff_cards: list[str] = []
    diff_count = 0

    for i, r in enumerate(rows_raw):
        has_diff = _row_has_diff(
            r["values"], file_labels,
            ignore_whitespace=ignore_whitespace, ignore_case=ignore_case,
        )
        if has_diff:
            diff_count += 1
            anchor = f"diff-{diff_count}"
        else:
            if hide_unchanged:
                continue
            anchor = f"row-{i}"

        vals = {
            "_group": r["group"], "_sub": r["sub_group"],
            "_name": r["name"], "_dim": r["dim"],
        }
        for lbl in file_labels:
            vals[f"f::{lbl}"] = r["values"].get(lbl, "")
        display_rows.append({
            "anchor": anchor, "has_diff": has_diff, "values": vals,
        })

        if has_diff:
            label_path = " › ".join(p for p in (r["group"], r["sub_group"]) if p)
            ctx = r["name"] or "(unnamed)"
            if label_path:
                ctx = f"{label_path} · {ctx}"
            diff_cards.append(_change_card(
                anchor=anchor, ref=f"#{diff_count}", ctx=ctx,
                values=[(lbl, _fmt_cell(r["values"].get(lbl, ""))) for lbl in file_labels],
                two_file_mode=two_file_mode,
            ))

    table_html = _render_table(columns_meta, display_rows, file_labels, two_file_mode)
    header = (
        '<div class="section-header">'
        '<h3>ComAp Parameter Comparison</h3>'
        f'<div class="sub">{len(display_rows)} row{"s" if len(display_rows) != 1 else ""} shown · '
        f'{len(file_labels)} file{"s" if len(file_labels) != 1 else ""}</div>'
        '</div>'
    )
    main = f'<main class="diff-main">{header}{_legend()}{table_html}</main>'
    side = _side_panel(diff_count, "".join(diff_cards))
    return _page(main + side), diff_count


# ── XLS / XLSX (ECU parameter) builder ────────────────────────────────────────

def build_xls_view(
    files_data: dict[str, dict],
    *,
    ignore_whitespace: bool = False,
    ignore_case: bool = False,
    hide_unchanged: bool = False,
    two_file_mode: bool = False,
    baseline: str | None = None,
    comparison: str | None = None,
    sheet_filter: Iterable[str] | None = None,
) -> tuple[str, int]:
    """Build the side-by-side HTML view for parsed ECU XLS/XLSX files."""
    if two_file_mode and baseline and comparison and baseline in files_data and comparison in files_data:
        file_labels = [baseline, comparison]
    else:
        file_labels = list(files_data.keys())
        two_file_mode = False

    if len(file_labels) < 2:
        return _page('<div class="diff-main"><div class="empty-state">'
                     'Need at least 2 files to compare.</div></div>'
                     + _side_panel(0, "")), 0

    sheets_wanted = set(sheet_filter) if sheet_filter is not None else {"Parameter", "Val_2D", "Val_3D"}

    sections_html: list[str] = []
    all_cards: list[str] = []
    total_diffs = 0

    columns_meta_base = [
        {"key": "_nr",   "label": "Nr", "kind": "id"},
        {"key": "_name", "label": "Name", "kind": "name"},
        {"key": "_loc",  "label": "Location", "kind": "id"},
    ]
    file_cols = [
        {"key": f"f::{lbl}", "label": lbl, "kind": "value", "file_label": lbl}
        for lbl in file_labels
    ]
    columns_meta = columns_meta_base + file_cols

    # ─── Parameter sheet ──────────────────────────────────────────────────────
    if "Parameter" in sheets_wanted:
        param_rows: list[dict] = []
        all_nrs: set[str] = set()
        for lbl in file_labels:
            all_nrs.update(files_data[lbl]["sheets"].get("Parameter", {}).keys())
        nrs_sorted = sorted(all_nrs, key=lambda x: (float(x) if str(x).replace(".", "").isdigit() else 0, x))
        for nr in nrs_sorted:
            values: dict[str, Any] = {}
            name = ""
            for lbl in file_labels:
                p = files_data[lbl]["sheets"].get("Parameter", {}).get(nr, {})
                values[lbl] = p.get("value")
                if not name:
                    name = p.get("name", "")
            param_rows.append({"nr": nr, "name": name, "loc": "Value", "values": values})

        s_rows, s_cards, s_count, total_diffs = _render_sheet_section(
            section_id="sheet-parameter",
            title="Parameter",
            rows_raw=param_rows,
            columns_meta=columns_meta,
            file_labels=file_labels,
            two_file_mode=two_file_mode,
            ignore_whitespace=ignore_whitespace,
            ignore_case=ignore_case,
            hide_unchanged=hide_unchanged,
            diff_offset=total_diffs,
        )
        sections_html.append(s_rows)
        all_cards.extend(s_cards)

    # ─── Val_2D sheet ─────────────────────────────────────────────────────────
    if "Val_2D" in sheets_wanted:
        v2d_rows: list[dict] = []
        all_nrs = set()
        for lbl in file_labels:
            all_nrs.update(files_data[lbl]["sheets"].get("Val_2D", {}).keys())
        nrs_sorted = sorted(all_nrs, key=lambda x: (float(x) if str(x).replace(".", "").isdigit() else 0, x))
        for nr in nrs_sorted:
            y_all: dict[str, list] = {}
            name = ""
            max_len = 0
            for lbl in file_labels:
                d = files_data[lbl]["sheets"].get("Val_2D", {}).get(nr, {})
                y = d.get("y_values", []) or []
                y_all[lbl] = y
                max_len = max(max_len, len(y))
                if not name:
                    name = d.get("name", "")
            for idx in range(max_len):
                values = {lbl: (y_all[lbl][idx] if idx < len(y_all[lbl]) else None) for lbl in file_labels}
                v2d_rows.append({"nr": nr, "name": name, "loc": f"y[{idx}]", "values": values})

        s_rows, s_cards, s_count, total_diffs = _render_sheet_section(
            section_id="sheet-val2d",
            title="Val_2D",
            rows_raw=v2d_rows,
            columns_meta=columns_meta,
            file_labels=file_labels,
            two_file_mode=two_file_mode,
            ignore_whitespace=ignore_whitespace,
            ignore_case=ignore_case,
            hide_unchanged=hide_unchanged,
            diff_offset=total_diffs,
        )
        sections_html.append(s_rows)
        all_cards.extend(s_cards)

    # ─── Val_3D sheet ─────────────────────────────────────────────────────────
    if "Val_3D" in sheets_wanted:
        v3d_rows: list[dict] = []
        all_nrs = set()
        for lbl in file_labels:
            all_nrs.update(files_data[lbl]["sheets"].get("Val_3D", {}).keys())
        nrs_sorted = sorted(all_nrs, key=lambda x: (float(x) if str(x).replace(".", "").isdigit() else 0, x))
        for nr in nrs_sorted:
            grids: dict[str, list[list]] = {}
            name = ""
            max_rows = 0
            max_cols = 0
            for lbl in file_labels:
                d = files_data[lbl]["sheets"].get("Val_3D", {}).get(nr, {})
                g = d.get("grid", []) or []
                grids[lbl] = g
                if g:
                    max_rows = max(max_rows, len(g))
                    max_cols = max(max_cols, max(len(r) for r in g))
                if not name:
                    name = d.get("name", "")
            for ri in range(max_rows):
                for ci in range(max_cols):
                    values = {}
                    for lbl in file_labels:
                        g = grids[lbl]
                        v = g[ri][ci] if ri < len(g) and ci < len(g[ri]) else None
                        values[lbl] = v
                    v3d_rows.append({"nr": nr, "name": name, "loc": f"[{ri}][{ci}]", "values": values})

        s_rows, s_cards, s_count, total_diffs = _render_sheet_section(
            section_id="sheet-val3d",
            title="Val_3D",
            rows_raw=v3d_rows,
            columns_meta=columns_meta,
            file_labels=file_labels,
            two_file_mode=two_file_mode,
            ignore_whitespace=ignore_whitespace,
            ignore_case=ignore_case,
            hide_unchanged=hide_unchanged,
            diff_offset=total_diffs,
        )
        sections_html.append(s_rows)
        all_cards.extend(s_cards)

    main = f'<main class="diff-main">{_legend()}{"".join(sections_html)}</main>'
    side = _side_panel(total_diffs, "".join(all_cards))
    return _page(main + side), total_diffs


def _render_sheet_section(
    *, section_id: str, title: str, rows_raw: list[dict],
    columns_meta: list[dict], file_labels: list[str], two_file_mode: bool,
    ignore_whitespace: bool, ignore_case: bool, hide_unchanged: bool,
    diff_offset: int,
) -> tuple[str, list[str], int, int]:
    """Render a sheet's rows into HTML + change cards.

    Returns ``(section_html, cards, sheet_diff_count, new_total_diffs)``.
    """
    display_rows: list[dict] = []
    cards: list[str] = []
    sheet_diff_count = 0
    total_diffs = diff_offset

    for i, r in enumerate(rows_raw):
        has_diff = _row_has_diff(
            r["values"], file_labels,
            ignore_whitespace=ignore_whitespace, ignore_case=ignore_case,
        )
        if has_diff:
            total_diffs += 1
            sheet_diff_count += 1
            anchor = f"diff-{total_diffs}"
        else:
            if hide_unchanged:
                continue
            anchor = f"{section_id}-row-{i}"

        vals = {"_nr": r["nr"], "_name": r["name"], "_loc": r["loc"]}
        for lbl in file_labels:
            vals[f"f::{lbl}"] = r["values"].get(lbl)
        display_rows.append({"anchor": anchor, "has_diff": has_diff, "values": vals})

        if has_diff:
            ctx = f"{r['name'] or '(unnamed)'} · {r['loc']}"
            cards.append(_change_card(
                anchor=anchor,
                ref=f"{title} #{r['nr']}",
                ctx=ctx,
                values=[(lbl, _fmt_cell(r["values"].get(lbl))) for lbl in file_labels],
                two_file_mode=two_file_mode,
            ))

    table_html = _render_table(columns_meta, display_rows, file_labels, two_file_mode)
    header = (
        f'<div class="section-header" id="{section_id}">'
        f'<h3>{html.escape(title)}</h3>'
        f'<div class="sub">{len(display_rows)} row{"s" if len(display_rows) != 1 else ""} shown · '
        f'{sheet_diff_count} difference{"s" if sheet_diff_count != 1 else ""}</div>'
        '</div>'
    )
    if not display_rows:
        body = f'{header}<div class="empty-state">No rows to display in this sheet.</div>'
    else:
        body = f'{header}{table_html}'
    return body, cards, sheet_diff_count, total_diffs
