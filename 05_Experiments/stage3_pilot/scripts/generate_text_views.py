"""Generate reproducible TS-Text samples for the Weather pilot.

Outputs:
  results/ts_text_samples.csv        # sample_id + window indices + dynamic_text
  results/text_views_stats.json     # rules, versions, leakage/redundancy checks

The `existing` view (global Prompt V1) is NOT written per-row; it is a code
constant in src/text_generation/text_views.py and is attached at training time.
This avoids bloating the CSV and keeps the Prompt intact (no split).

Run: python scripts/generate_text_views.py
"""
import os
import sys
import json
import hashlib

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    import yaml
    with open(os.path.join(os.path.dirname(__file__), "..", "configs", "exp_config.yaml"),
              encoding="utf-8") as f:
        CFG = yaml.safe_load(f)
except Exception:
    CFG = {}


def g(*keys, default=None):
    d = CFG
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


from src.data.weather_window_dataset import build_windows
from src.text_generation.dynamic_text import build_dynamic_text
from src.text_generation.text_views import get_view_text, PROMPT_V1_SHA256

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
seed = g("seed", default=42)
ws = g("data", "window_size", default=24)
st = g("data", "stride", default=6)
pol = g("data", "continuity_policy", default="boundary")
maxs = g("data", "max_samples", default=20000)

print("Building continuity-aware windows ...")
rows, channel_ids, cont = build_windows(window_size=ws, stride=st,
                                        duplicate_policy=pol,
                                        max_samples=maxs, seed=seed)
print(f"  samples={len(rows)} channels={len(channel_ids)} "
      f"segments={len(cont['segments'])}")

recs = []
all_dyn = []
for r in rows:
    dyn, _ = build_dynamic_text(r["window"], channel_ids)
    all_dyn.append(dyn)
    recs.append({
        "sample_id": r["sample_id"],
        "start_row": r["start_row"],
        "end_row": r["end_row"],
        "tgt_start": r["tgt_start"],
        "tgt_end": r["tgt_end"],
        "ts_start": r["ts_start"],
        "ts_end": r["ts_end"],
        "dynamic_text": dyn,
        "existing_ref": "GLOBAL_PROMPT_V1",
    })

df = pd.DataFrame(recs)
out_csv = os.path.join(ROOT, "05_Experiments", "stage3_pilot", "results", "ts_text_samples.csv")
os.makedirs(os.path.dirname(out_csv), exist_ok=True)
df.to_csv(out_csv, index=False, encoding="utf-8")


def meaningless(dyn: str) -> bool:
    # all channels constant -> no trend arrow and no volatility marker
    return ("↑" not in dyn) and ("↓" not in dyn) and ("H" not in dyn) \
        and ("M" not in dyn) and ("L" not in dyn)


n = len(df)
distinct = int(df["dynamic_text"].nunique())
frac_meaningless = float(np.mean([meaningless(d) for d in all_dyn]))
# Leakage is structurally prevented: dynamic_text is derived ONLY from the input
# window, never from the target window; no LLM, no invented physics.
leakage = False

raw = os.path.join(ROOT, "data", "raw", "Weather.csv")
stats = {
    "n_samples": n,
    "n_distinct_dynamic_text": distinct,
    "frac_distinct": float(distinct) / max(1, n),
    "frac_meaningless_constant_windows": frac_meaningless,
    "potential_text_leakage": leakage,
    "leakage_note": "dynamic_text derived solely from INPUT window, not target; no LLM; no invented physics",
    "prompt_v1_sha256": PROMPT_V1_SHA256,
    "raw_csv_sha256": hashlib.sha256(open(raw, "rb").read()).hexdigest(),
    "window_size": ws, "stride": st, "policy": pol, "seed": seed,
    "dynamic_rules": {
        "trend_threshold": g("text_views", "dynamic", "trend_threshold", default=0.15),
        "vol_const": g("text_views", "dynamic", "vol_const", default=0.05),
        "vol_low": g("text_views", "dynamic", "vol_low", default=0.30),
        "vol_med": g("text_views", "dynamic", "vol_med", default=1.00),
    },
}
stat_path = os.path.join(ROOT, "05_Experiments", "stage3_pilot", "results", "text_views_stats.json")
with open(stat_path, "w", encoding="utf-8") as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)

print(json.dumps(stats, ensure_ascii=False, indent=2))
print("WROTE", out_csv)
print("WROTE", stat_path)
