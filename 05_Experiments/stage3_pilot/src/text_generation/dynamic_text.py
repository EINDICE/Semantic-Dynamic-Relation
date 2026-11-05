"""Rule-based dynamic text construction from Weather windows.

Provides incremental, reproducible textual descriptions of local temporal
dynamics that are NOT present in the static variable descriptions.

All features are derived deterministically from the numeric window; no LLM is
used in v1. Every generated token has an explicit numeric basis recorded in
`window_features` so the text can be audited for leakage / redundancy.

Compliance:
- No physical meaning is invented for any channel (incl. CH_20/OT).
- Only stable channel IDs (CH_00..CH_20) and numeric features are used.
- The text is a compact, whitespace-delimited token stream (deterministic).
"""
import numpy as np

# Volatility levels by coefficient of variation (std / mean_abs)
VOL_CONST = 0.05
VOL_LOW = 0.30
VOL_MED = 1.00
TREND_THRESH = 0.15  # normalized |slope| over window range


def _vol_level(cv: float) -> str:
    if (not np.isfinite(cv)) or cv <= VOL_CONST:
        return "co"  # constant / near-constant
    if cv <= VOL_LOW:
        return "lo"
    if cv <= VOL_MED:
        return "me"
    return "hi"


def _trend_symbol(norm_slope: float) -> str:
    if norm_slope > TREND_THRESH:
        return "up"
    if norm_slope < -TREND_THRESH:
        return "dn"
    return "st"


def channel_dynamic_features(values) -> dict:
    """values: 1-D array (W,). Returns interpretable dynamic features."""
    v = np.asarray(values, dtype=np.float64)
    if v.size == 0 or not np.all(np.isfinite(v)):
        return {"trend": "na", "vol": "na", "extr": "na", "cv": float("nan"),
                "norm_slope": float("nan")}
    mean_abs = np.mean(np.abs(v)) + 1e-9
    std = float(np.std(v))
    cv = std / mean_abs
    x = np.arange(len(v), dtype=np.float64)
    slope = float(np.polyfit(x, v, 1)[0]) if len(v) >= 2 else 0.0
    rng = (float(np.max(v)) - float(np.min(v))) + 1e-9
    norm_slope = slope * len(v) / rng  # total change / range
    trend = _trend_symbol(norm_slope)
    vol = _vol_level(cv)
    imax, imin = int(np.argmax(v)), int(np.argmin(v))
    pos = lambda i: i / max(1, len(v) - 1)
    extr = "na"
    if vol != "co":
        if pos(imax) >= 0.7:
            extr = "pk"  # late peak
        elif pos(imin) <= 0.3:
            extr = "tr"  # early trough
    return {"trend": trend, "vol": vol, "extr": extr,
            "cv": float(cv), "norm_slope": float(norm_slope)}


_TREND_CHAR = {"up": "\u2191", "dn": "\u2193", "st": "\u2192", "na": "?"}
_VOL_CHAR = {"hi": "H", "me": "M", "lo": "L", "co": "C", "na": "?"}
_EXTR_CHAR = {"pk": "*", "tr": "^", "na": ""}


def channel_token(channel_id: str, feats: dict) -> str:
    return (f"{channel_id}{_TREND_CHAR[feats['trend']]}"
            f"{_VOL_CHAR[feats['vol']]}{_EXTR_CHAR[feats['extr']]}")


def build_dynamic_text(window, channel_ids) -> tuple:
    """window: (C, W) ndarray. Returns (dynamic_text, feature_table).

    dynamic_text is a compact, reproducible, whitespace-delimited token stream.
    """
    C, W = window.shape
    toks, table = [], []
    for i in range(C):
        feats = channel_dynamic_features(window[i])
        toks.append(channel_token(channel_ids[i], feats))
        table.append((channel_ids[i], feats))
    return " ".join(toks), table
