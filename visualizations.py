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
import pandas as pd
import numpy as np


def generate_plots(df_proc, client_name, output_dir="output/Graphs",
                   show_limits=False, nom_v=415.0, nom_f=50.0,
                   tol_v=1.0, tol_f=0.5):
    """
    Generate time-series plots for all available metrics.

    Returns:
        dict: mapping metric name -> file path of saved plot
    """
    os.makedirs(output_dir, exist_ok=True)
    paths = {}

    metrics = {
        "Avg_Voltage_LL": ("Voltage (V)", "#2563eb"),
        "Avg_kW": ("Power (kW)", "#16a34a"),
        "Avg_Current": ("Current (A)", "#dc2626"),
        "Avg_Frequency": ("Frequency (Hz)", "#ea580c"),
        "Avg_PF": ("Power Factor", "#0891b2"),
        "Avg_THD_F": ("Total Harmonic Distortion (THD)", "#9333ea"),
    }

    for col, (ylabel, color) in metrics.items():
        if col not in df_proc.columns or df_proc[col].dropna().empty:
            continue

        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(df_proc["Timestamp"], df_proc[col], color=color, linewidth=0.8)
        ax.set_title(f"{client_name} - {ylabel}", fontsize=13, fontweight="bold")
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_xlabel("")
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        fig.autofmt_xdate(rotation=30)

        if show_limits:
            if col == "Avg_Voltage_LL":
                ax.axhline(nom_v * (1 + tol_v / 100), color="red", ls="--", alpha=0.5, label="Upper Limit")
                ax.axhline(nom_v * (1 - tol_v / 100), color="red", ls="--", alpha=0.5, label="Lower Limit")
                ax.legend(fontsize="small")
            elif col == "Avg_Frequency":
                ax.axhline(nom_f * (1 + tol_f / 100), color="red", ls="--", alpha=0.5, label="Upper Limit")
                ax.axhline(nom_f * (1 - tol_f / 100), color="red", ls="--", alpha=0.5, label="Lower Limit")
                ax.legend(fontsize="small")

        plt.tight_layout()
        fname = os.path.join(output_dir, f"{client_name}_{col}.jpeg")
        fig.savefig(fname, dpi=150, bbox_inches="tight")
        plt.close(fig)
        paths[col] = fname

    return paths


def plot_load_change_snapshot(df_raw, event_ts, load_change, load_before, load_after,
                              client_name, output_dir="output/Snapshots"):
    """
    Generate a +-5 second snapshot around a load event showing V, I, F, kW.

    Returns:
        str: file path of saved snapshot image
    """
    os.makedirs(output_dir, exist_ok=True)

    df_win = df_raw[
        (df_raw["Timestamp"] >= event_ts - pd.Timedelta(seconds=5)) &
        (df_raw["Timestamp"] <= event_ts + pd.Timedelta(seconds=5))
    ].copy()

    if df_win.empty:
        return None

    fig, axes = plt.subplots(4, 1, figsize=(12, 13), sharex=True)
    fig.suptitle(
        f"Event: {event_ts.strftime('%H:%M:%S')} | "
        f"Load: {load_before:.0f} \u2192 {load_after:.0f} kW ({load_change:+.0f} kW)",
        fontsize=13, fontweight="bold"
    )

    # 1. Voltage
    v_cols_ln = ["U1_rms_AVG", "U2_rms_AVG", "U3_rms_AVG"]
    v_cols_ll = ["U12_rms_AVG", "U23_rms_AVG", "U31_rms_AVG"]
    v_to_plot = [c for c in v_cols_ln if c in df_win.columns]
    scale = np.sqrt(3) if v_to_plot else 1.0
    if not v_to_plot:
        v_to_plot = [c for c in v_cols_ll if c in df_win.columns]
    colors_v = ["#2563eb", "#dc2626", "#16a34a"]
    for i, c in enumerate(v_to_plot):
        axes[0].plot(df_win["Timestamp"], pd.to_numeric(df_win[c], errors="coerce") * scale,
                     label=c.split("_")[0], color=colors_v[i % 3], linewidth=0.8)
    if v_to_plot:
        axes[0].legend(loc="upper right", fontsize="small")
    axes[0].set_ylabel("Voltage (V)")
    axes[0].grid(True, alpha=0.3)

    # 2. Current
    i_cols = ["I1_rms_AVG", "I2_rms_AVG", "I3_rms_AVG"]
    colors_i = ["#2563eb", "#dc2626", "#16a34a"]
    for i, c in enumerate(i_cols):
        if c in df_win.columns:
            axes[1].plot(df_win["Timestamp"], pd.to_numeric(df_win[c], errors="coerce"),
                         label=c.split("_")[0], color=colors_i[i], linewidth=0.8)
    if any(c in df_win.columns for c in i_cols):
        axes[1].legend(loc="upper right", fontsize="small")
    axes[1].set_ylabel("Current (A)")
    axes[1].grid(True, alpha=0.3)

    # 3. Frequency
    if "Freq_AVG" in df_win.columns:
        axes[2].plot(df_win["Timestamp"], pd.to_numeric(df_win["Freq_AVG"], errors="coerce"),
                     color="#ea580c", linewidth=0.8, label="Frequency")
        axes[2].legend(loc="upper right", fontsize="small")
    axes[2].set_ylabel("Freq (Hz)")
    axes[2].grid(True, alpha=0.3)

    # 4. Power
    if "P_sum_AVG" in df_win.columns:
        axes[3].plot(df_win["Timestamp"], pd.to_numeric(df_win["P_sum_AVG"], errors="coerce") / 1000,
                     color="#16a34a", linewidth=0.8, label="Power")
        axes[3].legend(loc="upper right", fontsize="small")
    axes[3].set_ylabel("Power (kW)")
    axes[3].grid(True, alpha=0.3)

    axes[3].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.autofmt_xdate(rotation=30)
    plt.tight_layout()

    fname = os.path.join(output_dir, f"snap_{client_name}_{event_ts.strftime('%Y%m%d_%H%M%S')}.jpeg")
    fig.savefig(fname, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return fname


def generate_all_snapshots(df_raw, df_events, client_name, output_dir="output/Snapshots"):
    """Generate snapshots for all detected events. Returns list of file paths."""
    paths = []
    if df_events.empty:
        return paths
    for _, row in df_events.iterrows():
        path = plot_load_change_snapshot(
            df_raw,
            event_ts=row["Timestamp"],
            load_change=row["dKw"],
            load_before=row["Avg_kW"] - row["dKw"],
            load_after=row["Avg_kW"],
            client_name=client_name,
            output_dir=output_dir,
        )
        if path:
            paths.append(path)
    return paths


def save_compliance_table_as_image(df, filename, title_text, nom_v=415.0, nom_f=50.0):
    """
    Render the compliance DataFrame as a styled JPEG table image.

    Returns:
        str: path to saved image
    """
    if df.empty:
        return None

    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)

    display_cols = [
        "Timestamp", "dKw", "V_dev", "F_dev", "V_rec_s", "F_rec_s",
        "Compliance_Status", "Failure_Reasons",
    ]
    avail_cols = [c for c in display_cols if c in df.columns]
    plot_data = df[avail_cols].copy()

    # Format timestamps
    def format_range(row):
        s = row["Timestamp"]
        e = row.get("End_Timestamp", s)
        if pd.isna(e) or s == e:
            return s.strftime("%H:%M:%S")
        return s.strftime("%H:%M:") + f"{s.strftime('%S')}-{e.strftime('%S')}"

    plot_data["Timestamp"] = df.apply(format_range, axis=1)
    if "dKw" in plot_data.columns:
        plot_data["dKw"] = pd.to_numeric(plot_data["dKw"]).map("{:,.1f} kW".format)
    if "V_dev" in plot_data.columns:
        plot_data["V_dev"] = (pd.to_numeric(plot_data["V_dev"]) / nom_v * 100).map("{:+.1f}%".format)
    if "F_dev" in plot_data.columns:
        plot_data["F_dev"] = (pd.to_numeric(plot_data["F_dev"]) / nom_f * 100).map("{:+.1f}%".format)
    if "V_rec_s" in plot_data.columns:
        plot_data["V_rec_s"] = pd.to_numeric(plot_data["V_rec_s"]).map("{:,.1f}s".format)
    if "F_rec_s" in plot_data.columns:
        plot_data["F_rec_s"] = pd.to_numeric(plot_data["F_rec_s"]).map("{:,.1f}s".format)

    rename_map = {
        "Timestamp": "Event\nTime",
        "dKw": "Load\nChange\n(kW)",
        "V_dev": "Voltage\nDeviation\n(%)",
        "F_dev": "Frequency\nDeviation\n(%)",
        "V_rec_s": "Voltage\nRecovery\nTime (s)",
        "F_rec_s": "Frequency\nRecovery\nTime (s)",
        "Compliance_Status": "Status",
        "Failure_Reasons": "Compliance\nNotes",
    }
    plot_data.columns = [rename_map.get(c, c) for c in plot_data.columns]

    fig, ax = plt.subplots(figsize=(16, len(plot_data) * 0.8 + 2))
    ax.axis("off")

    tbl = ax.table(
        cellText=plot_data.values,
        colLabels=plot_data.columns,
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1, 3.5)

    # Find status column index
    status_col_idx = -1
    for i, col_name in enumerate(plot_data.columns):
        if "Status" in col_name:
            status_col_idx = i
            break

    for k, cell in tbl.get_celld().items():
        if k[0] == 0:
            cell.set_text_props(weight="bold", color="white")
            cell.set_facecolor("#003366")
        elif k[0] % 2 == 0:
            cell.set_facecolor("#f2f2f2")
        if k[1] == status_col_idx and k[0] > 0:
            cell_val = plot_data.iloc[k[0] - 1, status_col_idx]
            cell.set_text_props(
                color="green" if "Pass" in str(cell_val) else "red",
                weight="bold",
            )

    plt.title(title_text, fontsize=15, weight="bold", pad=30)
    plt.savefig(filename, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return filename
