"""Alignment-quality evaluation utilities.

Includes linear CKA, RSA (Spearman), CCA (sklearn), and a TS-specific linear
probe. These measure representation structure and modality-specific retention;
they do NOT by themselves prove task usefulness.
"""
import numpy as np

try:
    from sklearn.cross_decomposition import CCA
    from scipy.stats import spearmanr
except Exception:  # pragma: no cover
    CCA = None
    spearmanr = None


def linear_cka(X, Y, reg=1e-6):
    """Linear CKA between two representation matrices (n, d1)/(n, d2)."""
    X = np.asarray(X, dtype=np.float64)
    Y = np.asarray(Y, dtype=np.float64)
    X = X - X.mean(0, keepdims=True)
    Y = Y - Y.mean(0, keepdims=True)
    X = X @ np.linalg.inv(X.T @ X + reg * np.eye(X.shape[1])) @ X.T
    Y = Y @ np.linalg.inv(Y.T @ Y + reg * np.eye(Y.shape[1])) @ Y.T
    cov = np.sum(X * Y) / X.shape[0]
    var = np.sqrt(np.sum(X * X) * np.sum(Y * Y)) / X.shape[0]
    return float(cov / (var + 1e-12))


def rsa(X, Y):
    """Representational similarity (Spearman over pairwise dist vectors)."""
    if spearmanr is None:
        return float("nan")
    X, Y = np.asarray(X, dtype=np.float64), np.asarray(Y, dtype=np.float64)
    dx = 1 - np.corrcoef(X)
    dy = 1 - np.corrcoef(Y)
    r, _ = spearmanr(dx.ravel(), dy.ravel())
    return float(r)


def cca_correlation(X, Y, n_comp=2):
    if CCA is None:
        return float("nan")
    X, Y = np.asarray(X, dtype=np.float64), np.asarray(Y, dtype=np.float64)
    n = min(n_comp, X.shape[1], Y.shape[1], X.shape[0] - 1)
    model = CCA(n_components=max(1, n))
    model.fit(X, Y)
    u, v = model.transform(X, Y)
    k = min(u.shape[1], v.shape[1])
    corr = [float(np.corrcoef(u[:, i], v[:, i])[0, 1]) for i in range(k)]
    return float(np.mean(corr)) if corr else float("nan")


def ts_specific_probe(ts_repr, y, test_size=0.3, seed=42):
    """Linear probe: can TS repr predict y? Returns (train_r2, test_r2)."""
    from sklearn.linear_model import LinearRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import r2_score
    X = np.asarray(ts_repr, dtype=np.float64)
    yy = np.asarray(y, dtype=np.float64).ravel()
    Xtr, Xte, ytr, yte = train_test_split(X, yy, test_size=test_size,
                                          random_state=seed)
    reg = LinearRegression().fit(Xtr, ytr)
    return float(r2_score(ytr, reg.predict(Xtr))), float(r2_score(yte, reg.predict(Xte)))
