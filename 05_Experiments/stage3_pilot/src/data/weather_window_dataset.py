"""Continuity-aware Weather window dataset with attached text views.

Reuses src/continuity.py (boundary policy) from the main project.
Uses MASKED_VIEW (-9999 -> NaN) and excludes windows containing NaN.
All choices are pilot-candidate values (see configs/exp_config.yaml).
"""
import os
import sys
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

import importlib.util as _ilu

_continuity_path = os.path.join(PROJECT_ROOT, "src", "continuity.py")
_spec = _ilu.spec_from_file_location("weather_pilot_continuity", _continuity_path)
_continuity_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_continuity_mod)
check_time_continuity = _continuity_mod.check_time_continuity
validate_window_rows = _continuity_mod.validate_window_rows

RAW_CSV = os.path.join(PROJECT_ROOT, "data", "raw", "Weather.csv")
SENTINEL = -9999.0


def load_weather_raw():
    df = pd.read_csv(RAW_CSV, encoding="utf-8")
    t = pd.to_datetime(df["date"])
    vals = df.drop(columns=["date"]).to_numpy(dtype=np.float64)  # (N, C)
    return df, t, vals


def masked_values(vals):
    v = vals.copy()
    v[v == SENTINEL] = np.nan
    return v


def build_windows(window_size=24, stride=6, duplicate_policy="boundary",
                  max_samples=None, seed=42):
    """Return (rows, channel_ids, continuity).

    Each row: dict with sample_id, start_row, end_row (inclusive), tgt_start,
    tgt_end (inclusive), ts_start, ts_end, window (C,W) float32, target (C,W).
    Windows containing NaN are excluded. Deterministic given seed/params.
    """
    df, t, vals = load_weather_raw()
    mv = masked_values(vals)
    cont = check_time_continuity(t, "10min", duplicate_policy)
    C = vals.shape[1]
    channel_ids = [f"CH_{i:02d}" for i in range(C)]
    rows = []
    for seg in cont["segments"]:
        s0, s1, n = seg["start_row"], seg["end_row"], seg["n_rows"]
        for start in range(s0, s1 - window_size + 2, stride):
            end = start + window_size
            if end > s1 + 1:
                break
            ok = validate_window_rows(list(range(start, end)), t, cont,
                                     window_size, "10min")
            if not ok.get("valid", False):
                continue
            w = mv[start:end].T.astype(np.float32)      # (C, W)
            if np.any(np.isnan(w)):
                continue
            tgt_end = end + window_size
            if tgt_end > s1 + 1:
                continue
            wt = mv[end:tgt_end].T.astype(np.float32)   # (C, W)
            if np.any(np.isnan(wt)):
                continue
            rows.append({
                "sample_id": len(rows),
                "start_row": int(start),
                "end_row": int(end - 1),
                "tgt_start": int(end),
                "tgt_end": int(tgt_end - 1),
                "ts_start": str(t.iloc[start]),
                "ts_end": str(t.iloc[end - 1]),
                "window": w,
                "target": wt,
            })
            if max_samples and len(rows) >= max_samples:
                return rows, channel_ids, cont
    return rows, channel_ids, cont
