"""Cross-modal model: TS encoder + (optional) text encoder + forecast head.

For TS-only groups, text_feat is None and no alignment loss is used.
For TS+Text groups, projection heads produce matched TS/text reps for InfoNCE.
"""
import torch.nn as nn

from src.encoders.ts_encoder import TSEncoder
from src.encoders.text_encoder import TextEncoder


class CrossModalModel(nn.Module):
    def __init__(self, c_in=21, win=24, pred_len=24, d_ts=32, d_text=32,
                 d_proj=32, vocab_dim=4096):
        super().__init__()
        self.ts_enc = TSEncoder(c_in, win, d_ts)
        self.text_enc = TextEncoder(vocab_dim, d_text)
        self.ts_proj = nn.Linear(d_ts, d_proj)
        self.text_proj = nn.Linear(d_text, d_proj)
        self.fcst = nn.Linear(d_ts, c_in * pred_len)
        self.c_in, self.pred_len = c_in, pred_len

    def forward(self, x, text_feat=None):
        h_ts = self.ts_enc(x)                       # (B, d_ts)
        out = self.fcst(h_ts).view(-1, self.c_in, self.pred_len)
        reps = {"ts": self.ts_proj(h_ts)}
        if text_feat is not None:
            h_text = self.text_proj(self.text_enc(text_feat))
            reps["text"] = h_text
        return out, reps
