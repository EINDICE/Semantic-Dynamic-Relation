"""InfoNCE contrastive loss between TS and text representations."""
import torch
import torch.nn.functional as F


def info_nce(ts, text, temperature=0.1):
    """ts, text: (B, d). Aligned pairs are the diagonal (i,i)."""
    ts = F.normalize(ts, dim=-1)
    text = F.normalize(text, dim=-1)
    logits = torch.matmul(ts, text.t()) / max(temperature, 1e-6)  # (B,B)
    labels = torch.arange(ts.size(0), device=ts.device)
    return 0.5 * (F.cross_entropy(logits, labels) +
                  F.cross_entropy(logits.t(), labels))
