"""Minimal learnable time-series encoder (1D-CNN -> global pool).

Small, self-contained; not copied from third-party methods. Suitable for pilot
smoke tests; later can be swapped for PatchTST/TimesNet-style backbones.
"""
import torch.nn as nn


class TSEncoder(nn.Module):
    def __init__(self, c_in=21, win=24, d_model=32, hidden=64):
        super().__init__()
        self.conv1 = nn.Conv1d(c_in, hidden, kernel_size=3, padding=1)
        self.conv2 = nn.Conv1d(hidden, d_model, kernel_size=3, padding=1)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.act = nn.ReLU()

    def forward(self, x):  # x: (B, C, W)
        h = self.act(self.conv1(x))
        h = self.act(self.conv2(h))      # (B, d_model, W)
        return self.pool(h).squeeze(-1)  # (B, d_model)
