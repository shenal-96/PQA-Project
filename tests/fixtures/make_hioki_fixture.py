"""Generate a deterministic Hioki/generic-format CSV fixture for the parity tests.

The data is fully deterministic (no RNG) and crafted to exercise the real
analysis path: a steady base load, a load **increase** event (voltage + freq dip
then recovery) and a load **decrease** event (voltage + freq overshoot then
recovery). Run this module to regenerate ``hioki_sample.csv`` next to it.

Columns match what ``core.analysis.load_and_prepare_csv`` expects for the
Hioki/generic branch:
  PC Time (DD/MM/YYYY HH:MM:SS) · U12/U23/U31_rms_AVG (L-L V) ·
  I1/I2/I3_rms_AVG (A) · Freq_AVG (Hz) · P_sum_AVG (W) · PF_sum_AVG
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

NOM_V = 415.0          # nominal L-L voltage
NOM_F = 50.0           # nominal frequency
N = 150               # samples (1 Hz -> 150 s)
START = datetime(2026, 1, 15, 9, 0, 0)


def _transient(arr: np.ndarray, t: np.ndarray, t_event: float, amp: float, tau: float) -> None:
    """Add an exponentially-decaying transient ``amp * exp(-(t-te)/tau)`` for t>=te."""
    mask = t >= t_event
    arr[mask] += amp * np.exp(-(t[mask] - t_event) / tau)


def build() -> pd.DataFrame:
    t = np.arange(N, dtype=float)  # seconds
    times = [START + timedelta(seconds=int(s)) for s in t]

    # Load profile (kW): base 120, +220 at 50 s, -160 at 100 s.
    p_kw = np.full(N, 120.0)
    p_kw[50:] += 220.0
    p_kw[100:] -= 160.0

    v = np.full(N, NOM_V)
    f = np.full(N, NOM_F)
    # Event 1 (increase): voltage + frequency dip, then recover.
    _transient(v, t, 50, -16.0, 0.9)
    _transient(f, t, 50, -0.45, 0.8)
    # Event 2 (decrease): voltage + frequency overshoot, then recover.
    _transient(v, t, 100, +14.0, 0.9)
    _transient(f, t, 100, +0.33, 0.8)

    pf = np.full(N, 0.90)
    p_w = p_kw * 1000.0  # pipeline divides P_sum_AVG by 1000 internally
    current = p_w / (np.sqrt(3.0) * v * pf)  # per-phase A

    return pd.DataFrame({
        "PC Time": [tm.strftime("%d/%m/%Y %H:%M:%S") for tm in times],
        "U12_rms_AVG": np.round(v, 3),
        "U23_rms_AVG": np.round(v, 3),
        "U31_rms_AVG": np.round(v, 3),
        "I1_rms_AVG": np.round(current, 3),
        "I2_rms_AVG": np.round(current, 3),
        "I3_rms_AVG": np.round(current, 3),
        "Freq_AVG": np.round(f, 4),
        "P_sum_AVG": np.round(p_w, 1),
        "PF_sum_AVG": np.round(pf, 3),
    })


def main() -> str:
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hioki_sample.csv")
    build().to_csv(out, index=False)
    return out


if __name__ == "__main__":
    print("wrote", main())
