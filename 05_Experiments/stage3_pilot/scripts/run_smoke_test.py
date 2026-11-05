"""Minimal TS-only vs TS+Text contrast experiment — Smoke Test.

Runs groups A(ts_only)/B(ts+existing, no align)/C(ts+dynamic, align)/D(ts+both,
align) for a few steps to validate: data loading -> forward -> forecast loss ->
(optional) InfoNCE align loss -> backward -> device/memory.

Writes results/smoke_test_results.json. No large training; uses <=3000 windows.

Run: python scripts/run_smoke_test.py
"""
import os
import sys
import json

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
from sklearn.feature_extraction.text import TfidfVectorizer

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
from src.text_generation.text_views import get_view_text
from src.models.cross_modal_model import CrossModalModel
from src.alignment.contrastive import info_nce

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
seed = g("seed", default=42)
torch.manual_seed(seed)
np.random.seed(seed)

ws = g("data", "window_size", default=24)
st = g("data", "stride", default=6)
pol = g("data", "continuity_policy", default="boundary")
maxs = g("data", "max_samples", default=20000)
pred_len = g("data", "pred_len", default=24)
split_r = g("data", "split_ratios", default=[0.70, 0.85])
bs = g("training", "batch_size", default=64)
lr = g("training", "lr", default=1e-3)
temp = g("training", "contrastive_temperature", default=0.1)
fw = g("training", "forecast_weight", default=1.0)
aw = g("training", "align_weight", default=0.5)
vocab_dim = g("model", "vocab_dim", default=4096)
device_str = g("training", "device", default="auto")
device = ("cuda" if torch.cuda.is_available() else "cpu") if device_str == "auto" else device_str

print("Building windows (smoke subset) ...")
rows, channel_ids, cont = build_windows(window_size=ws, stride=st,
                                        duplicate_policy=pol,
                                        max_samples=min(maxs, 3000), seed=seed)
N = len(rows)
n_tr = int(split_r[0] * N)
n_val = int(split_r[1] * N)
print(f"  N={N} n_tr={n_tr} n_val={n_val} n_te={N - n_val}")


def make_text(view):
    return [get_view_text(view, build_dynamic_text(r["window"], channel_ids)[0])
            for r in rows]


texts_all = make_text("both")
print("Fitting TF-IDF on TRAIN texts only (leakage control) ...")
vec = TfidfVectorizer(max_features=vocab_dim,
                      min_df=g("text_views", "tfidf_min_df", default=2))
vec.fit([texts_all[i] for i in range(n_tr)])
Xall = vec.transform(texts_all).toarray().astype(np.float32)
vocab_dim = len(vec.vocabulary_)
print(f"  vocab_dim={vocab_dim}")


class DS(Dataset):
    def __init__(self, idx, use_text, vocab_dim):
        self.idx = idx
        self.use_text = use_text
        self.vocab_dim = vocab_dim

    def __len__(self):
        return len(self.idx)

    def __getitem__(self, k):
        r = rows[self.idx[k]]
        x = torch.from_numpy(r["window"])
        y = torch.from_numpy(r["target"])
        # TS-only groups still return a dummy tensor so default_collate works;
        # run_group passes None to the model so the text branch is unused.
        t = torch.from_numpy(Xall[self.idx[k]]) if self.use_text \
            else torch.zeros(self.vocab_dim)
        return x, y, t


def loader(idx, use_text, shuf):
    return DataLoader(DS(idx, use_text, vocab_dim), batch_size=bs, shuffle=shuf)


def run_group(name, view, use_align, epochs=5):
    print(f"\n=== Group {name} (view={view}, align={use_align}) ===")
    use_text = view != "none"
    tr_idx = list(range(0, n_tr))
    va_idx = list(range(n_tr, n_val))
    tr_ld = loader(tr_idx, use_text, True)
    va_ld = loader(va_idx, use_text, False)
    model = CrossModalModel(c_in=21, win=ws, pred_len=pred_len,
                            vocab_dim=vocab_dim).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    log = []
    for ep in range(epochs):
        model.train()
        tot_f, tot_a, nb = 0.0, 0.0, 0
        for x, y, t in tr_ld:
            x, y = x.to(device), y.to(device)
            if t is not None:
                t = t.to(device)
            opt.zero_grad()
            out, reps = model(x, t if use_text else None)
            lf = fw * ((out - y) ** 2).mean()
            la = 0.0
            if use_align and "text" in reps:
                la = aw * info_nce(reps["ts"], reps["text"], temp)
                tot_a += la.item()
            loss = lf + (la if isinstance(la, float) else la)
            loss.backward()
            opt.step()
            tot_f += lf.item()
            nb += 1
        val_f = 0.0
        with torch.no_grad():
            for x, y, t in va_ld:
                x, y = x.to(device), y.to(device)
                if t is not None:
                    t = t.to(device)
                out = model(x, t if use_text else None)[0]
                val_f += ((out - y) ** 2).mean().item()
        val_f /= max(1, len(va_ld))
        log.append({"epoch": ep, "train_f": tot_f / nb,
                    "train_align": tot_a / nb, "val_f": val_f})
        print(f"  ep{ep} train_f={tot_f/nb:.4f} train_align={tot_a/nb:.4f} val_f={val_f:.4f}")
    mem = torch.cuda.memory_allocated(device) / 1e6 if device == "cuda" else 0.0
    return {"group": name, "view": view, "align": use_align, "vocab_dim": vocab_dim,
            "device": device, "n_params": sum(p.numel() for p in model.parameters()),
            "log": log, "final_val_mse": val_f, "gpu_mem_mb": mem}


results = []
for grp in g("groups", default=[]):
    results.append(run_group(grp["name"], grp["text_view"], grp["use_align"],
                             epochs=g("training", "epochs_smoke", default=5)))

out_path = os.path.join(ROOT, "05_Experiments", "stage3_pilot", "results", "smoke_test_results.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
json.dump(results, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\nWROTE", out_path)
