"""common.py — shared loading and stats for the bid-ask lens analyses."""
import csv, math, os
import numpy as np

DATA = os.path.join(os.path.dirname(__file__), "data")

PIP = {"R_10": 3, "R_25": 3, "R_50": 4, "R_75": 4, "R_100": 2, "1HZ100V": 2,
       "CRASH500": 3, "CRASH1000": 3, "BOOM500": 3, "BOOM1000": 3,
       "JD10": 2, "JD25": 2, "JD50": 2, "JD75": 2, "JD100": 2, "stpRNG": 1}


def load(sym):
    """Return dict of numpy arrays: epoch, quote, bid, ask, spread, mid, skew (pip units)."""
    path = os.path.join(DATA, f"{sym}.csv")
    ep, q, b, a = [], [], [], []
    with open(path) as f:
        r = csv.reader(f)
        next(r)
        last = None
        for row in r:
            e = int(row[0])
            if last is not None and e <= last:
                continue  # dedupe/reorder guard
            last = e
            ep.append(e); q.append(float(row[1])); b.append(float(row[2])); a.append(float(row[3]))
    pip = PIP[sym]
    scale = 10 ** pip
    ep = np.array(ep); q = np.array(q) * scale; b = np.array(b) * scale; a = np.array(a) * scale
    return dict(sym=sym, pip=pip, epoch=ep, quote=q, bid=b, ask=a,
                spread=a - b, mid=(a + b) / 2, skew=(a + b) / 2 - q)


def rolling_sigma(quote, window=300, jump_mult=6.0):
    """Rolling no-jump std of 1-tick steps (pip units). Jump threshold via global MAD."""
    st = np.diff(quote)
    mad = np.median(np.abs(st - np.median(st))) or 1.0
    thr = jump_mult * 1.4826 * mad
    nj = np.abs(st) <= thr
    sq = np.where(nj, st * st, 0.0)
    cn = nj.astype(float)
    csq = np.cumsum(sq); ccn = np.cumsum(cn)
    sig = np.full(len(st), np.nan)
    w = window
    csq = np.concatenate([[0.0], csq]); ccn = np.concatenate([[0.0], ccn])
    for i in range(w, len(st) + 1):
        n = ccn[i] - ccn[i - w]
        if n >= w * 0.5:
            sig[i - 1] = math.sqrt((csq[i] - csq[i - w]) / n)
    return sig, thr, nj


def pearson_t(x, y):
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    n = len(x)
    if n < 10 or x.std() == 0 or y.std() == 0:
        return np.nan, np.nan, n
    r = float(np.corrcoef(x, y)[0, 1])
    t = r * math.sqrt((n - 2) / max(1e-12, 1 - r * r))
    return r, t, n


def block_perm_pvalue(series, event_idx, pre, stat_fn, nperm=2000, seed=7):
    """Permutation test: stat over pre-event windows vs random placements."""
    rng = np.random.default_rng(seed)
    n = len(series)
    obs = stat_fn(series, event_idx, pre)
    if np.isnan(obs):
        return obs, np.nan
    cnt = 0; vals = []
    for _ in range(nperm):
        fake = rng.integers(pre, n - 1, size=len(event_idx))
        v = stat_fn(series, fake, pre)
        vals.append(v)
        if abs(v) >= abs(obs):
            cnt += 1
    return obs, (cnt + 1) / (nperm + 1)
