"""Minimal learnable text encoder: TF-IDF features -> MLP projection.

TF-IDF is fit deterministically (sklearn) on training texts (no leakage);
this module only learns a linear+ReLU projection. No gpt2/sentence-transformers
dependency in v1.
"""
import torch.nn as nn


class TextEncoder(nn.Module):
    def __init__(self, vocab_dim, d_text=32):
        super().__init__()
        self.proj = nn.Linear(vocab_dim, d_text)
        self.act = nn.ReLU()

    def forward(self, x):  # x: (B, vocab_dim)
        return self.act(self.proj(x))
