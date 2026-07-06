"""holdout_tests.py — pre-registered holdout confirmation for the two surviving
exploratory signals from session 1 (data epoch <= 1783307443):

  H1 (CONFIRMED in-sample, needs holdout per protocol): JD100 sub-pip leak —
     slope(step_{t+1} ~ skew_t) = +1. In-sample: +1.12 ± 0.23, n=40.6k, p=9.6e-7.
     Holdout pass criterion (pre-registered): slope > 0 with one-sided p < 0.05
     AND slope consistent with 1 (|t vs 1| < 2).

  H2 (EXPLORATORY in-sample): parity-at-halfpip. NOTE ON DIRECTION: the session-1
     checkpoint phrased it "EVEN at -0.5 / ODD at +0.5" but under common.py's fixed
     convention skew = mid - quote, reproducing the test on the exact session-1 data
     gives the OPPOSITE alignment: ODD at skew=-0.5 (51.2%), EVEN at skew=+0.5
     (53.0%), pooled 1444/2772 = 52.1%, one-sided binomial p = 0.013. The ad-hoc
     session-1 script evidently used skew = quote - mid. The direction pre-registered
     here is the one actually present in-sample under the fixed convention:
     success = ODD after skew=-0.5, EVEN after skew=+0.5.
     Holdout pass criterion (pre-registered): pooled one-sided binomial p < 0.05.

Holdout = all ticks with epoch >= FRESH_START (session 2, collected 2026-07-06,
fully disjoint from every tick used to form the hypotheses).
"""
import sys, math, json
import numpy as np
from scipy import stats
from common import load
from ledger import log_test

FRESH_START = 1783320000  # session gap: session1 ends 1783307443, session2 starts 1783329220


def fresh(sym):
    d = load(sym)
    m = d["epoch"] >= FRESH_START
    return {k: (v[m] if isinstance(v, np.ndarray) else v) for k, v in d.items()}


def consecutive(d):
    iv = np.diff(d["epoch"])
    modal = int(np.bincount(iv[iv < 10]).argmax())
    ok = iv == modal
    step = (d["quote"][1:] - d["quote"][:-1])[ok]
    skew = d["skew"][:-1][ok]
    nxt = d["quote"][1:][ok]
    return step, skew, nxt


def h1_leak(sym="JD100"):
    d = fresh(sym)
    step, skew, _ = consecutive(d)
    n = len(step)
    if n < 2000 or skew.std() == 0:
        return dict(h="H1", sym=sym, n=int(n), verdict="insufficient holdout data")
    b, a = np.polyfit(skew, step, 1)
    resid = step - (a + b * skew)
    se = resid.std() / (skew.std() * math.sqrt(n))
    t0, t1 = b / se, (b - 1) / se
    p_one = 1 - stats.norm.cdf(t0)
    passed = (p_one < 0.05) and (abs(t1) < 2)
    log_test(instrument=sym, seed=1,
             hypothesis="HOLDOUT: skew leaks sub-pip spot, slope=+1 (pre-registered)",
             stat=f"slope={b:.3f}±{se:.3f}", n=n, t=float(t0),
             note=f"one-sided p={p_one:.2e}; t vs 1: {t1:+.2f}; PASS={passed}")
    return dict(h="H1", sym=sym, n=int(n), slope=float(b), se=float(se),
                t_vs_zero=float(t0), t_vs_one=float(t1), p_one_sided=float(p_one),
                PASS=bool(passed))


def h2_parity(sym="JD100"):
    d = fresh(sym)
    step, skew, nxt = consecutive(d)
    digit = (np.round(nxt).astype(int)) % 10
    even = digit % 2 == 0
    neg = np.isclose(skew, -0.5)
    pos = np.isclose(skew, +0.5)
    # aligned success (pre-registered, see module docstring):
    # ODD after skew=-0.5, EVEN after skew=+0.5
    succ = int((~even[neg]).sum() + even[pos].sum())
    n = int(neg.sum() + pos.sum())
    if n < 200:
        return dict(h="H2", sym=sym, n=n, verdict="insufficient holdout data")
    p_one = stats.binomtest(succ, n, 0.5, alternative="greater").pvalue
    rate = succ / n
    # per-side detail
    d_neg = dict(n=int(neg.sum()), odd_rate=float((~even[neg]).mean()) if neg.any() else None)
    d_pos = dict(n=int(pos.sum()), even_rate=float(even[pos].mean()) if pos.any() else None)
    passed = p_one < 0.05
    log_test(instrument=sym, seed=1,
             hypothesis="HOLDOUT: parity at halfpip skew (ODD@-0.5 / EVEN@+0.5, skew=mid-quote) (pre-registered)",
             stat=f"success {succ}/{n} = {rate:.4f}", n=n,
             t=float((rate - 0.5) / math.sqrt(0.25 / n)),
             note=f"one-sided binomial p={p_one:.3g}; neg={d_neg}; pos={d_pos}; PASS={passed}")
    return dict(h="H2", sym=sym, n=n, success=succ, rate=float(rate),
                p_one_sided=float(p_one), side_neg=d_neg, side_pos=d_pos,
                PASS=bool(passed))


if __name__ == "__main__":
    res = [h1_leak(), h2_parity()]
    for r in res:
        print(json.dumps(r))
    json.dump(res, open("results/holdout_tests.json", "w"), indent=1)
