"""seed2_spread_sigma.py — Seed 2: does spread track realized volatility?

Design (per addendum): Volatility indices are the clean lab (no jumps). If the spread
carries a volatility signal it must show here first. Then transfer to JD100.

Method:
 - residualize spread against spot (spread_resid = spread - OLS(price)), since Seed 1
   may show spread ~ c*price deterministically; only the residual can carry signal.
 - rolling realized sigma (300-tick window) of no-jump steps.
 - contemporaneous Pearson r(spread_resid, sigma) + lead/lag cross-correlation
   at lags -120..+120 ticks (negative lag = spread LEADS sigma).
Every test is logged to the central ledger.
"""
import json, sys
import numpy as np
from common import load, rolling_sigma, pearson_t, PIP
from ledger import log_test

LAGS = [-120, -60, -30, -10, -5, -1, 0, 1, 5, 10, 30, 60, 120]

def analyze(sym, window=300):
    d = load(sym)
    q, sp = d["quote"], d["spread"]
    if len(q) < window * 3:
        return None
    b, a = np.polyfit(q, sp, 1)
    spr = sp - (a + b * q)          # spread residual
    sig, thr, _ = rolling_sigma(q, window=window)
    # align: sigma[i] is std of steps ending at tick i+1; spread at tick i+1
    spr_t = spr[1:]
    out = dict(sym=sym, n=int(len(q)), jump_thr_pips=float(thr), lags={})
    for lag in LAGS:
        # corr(spread_resid[t+lag_shift]...) — negative lag: spread earlier than sigma
        if lag < 0:
            x = spr_t[:lag]; y = sig[-lag:]
        elif lag > 0:
            x = spr_t[lag:]; y = sig[:-lag]
        else:
            x = spr_t; y = sig
        r, t, n = pearson_t(x, y)
        out["lags"][lag] = dict(r=None if np.isnan(r) else float(r),
                                t=None if np.isnan(t) else float(t), n=int(n))
        if lag in (-60, -10, 0) and not np.isnan(r):
            # effective sample size correction for autocorrelation: n_eff ~ n / window
            n_eff = max(3, n / window)
            t_eff = r * np.sqrt((n_eff - 2) / max(1e-12, 1 - r * r))
            log_test(instrument=sym, seed=2,
                     hypothesis=f"spread_resid ~ sigma (lag {lag})",
                     stat=f"r={r:.4f}", n=n, t=float(t_eff),
                     note=f"t adjusted for autocorr with n_eff=n/{window}")
    return out

if __name__ == "__main__":
    syms = sys.argv[1:] or ["R_10", "R_25", "R_50", "R_75", "R_100", "1HZ100V",
                            "JD10", "JD25", "JD50", "JD75", "JD100"]
    res = []
    for s in syms:
        try:
            r = analyze(s)
        except FileNotFoundError:
            continue
        if r:
            res.append(r)
            l0 = r["lags"][0]
            cands = [(v["r"], k) for k, v in r["lags"].items() if v["r"] is not None]
            if not cands:
                print(f"{s:9s} n={r['n']:6d} spread residual has zero variance -> Seed 2 undefined")
                continue
            best = max(cands)
            print(f"{s:9s} n={r['n']:6d} r(lag0)={l0['r']:+.4f} "
                  f"best lag={best[1]:+4d} r={best[0]:+.4f}")
    json.dump(res, open("results/seed2_spread_sigma.json", "w"), indent=1)
