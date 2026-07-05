"""seed1_structure.py — Seed 1: what IS the spread on each instrument?

Questions, per symbol:
 1. Spread distribution: constant? quantized? how many distinct values?
 2. Is spread a deterministic function of spot (spread ~ c*price rounded to pip)?
    -> regress spread on quote; if residual std << 1 pip, the spread carries ZERO
       information beyond spot and Seeds 2/3 collapse to spot-only statements.
 3. Skew: mid - quote. Zero? rounding artifact (|skew| <= 0.5 pip)? or real signal?
"""
import json, sys
import numpy as np
from common import load, PIP

def analyze(sym):
    d = load(sym)
    sp, q, sk = d["spread"], d["quote"], d["skew"]
    n = len(q)
    if n < 500:
        return None
    uniq = np.unique(np.round(sp, 3))
    # OLS spread = a + b*price
    b, a = np.polyfit(q, sp, 1)
    resid = sp - (a + b * q)
    # deterministic model: spread = round(c * price) at pip resolution, c = mean ratio
    c = float(np.mean(sp / q))
    resid_round = sp - np.round(c * q)
    out = dict(
        sym=sym, n=int(n),
        spread_pips=dict(mean=float(sp.mean()), min=float(sp.min()), max=float(sp.max()),
                         std=float(sp.std()), n_unique=int(len(uniq)),
                         values=[float(v) for v in uniq[:12]]),
        spread_bps=float((sp / q).mean() * 1e4),
        ols=dict(slope_bps=float(b * 1e4), intercept_pips=float(a),
                 resid_std_pips=float(resid.std())),
        det_round_model=dict(c_bps=float(c * 1e4),
                             resid_std_pips=float(resid_round.std()),
                             frac_exact=float(np.mean(np.abs(resid_round) < 0.5001))),
        skew_pips=dict(mean=float(sk.mean()), std=float(sk.std()),
                       min=float(sk.min()), max=float(sk.max()),
                       frac_zero=float(np.mean(np.abs(sk) < 1e-9)),
                       frac_within_half_pip=float(np.mean(np.abs(sk) <= 0.5001))),
    )
    return out

if __name__ == "__main__":
    syms = sys.argv[1:] or list(PIP)
    res = []
    for s in syms:
        try:
            r = analyze(s)
        except FileNotFoundError:
            continue
        if r:
            res.append(r)
            print(f"{s:9s} n={r['n']:6d} spr={r['spread_pips']['mean']:9.2f}p "
                  f"({r['spread_bps']:.3f}bps) uniq={r['spread_pips']['n_unique']:3d} "
                  f"OLSresid={r['ols']['resid_std_pips']:.3f}p "
                  f"round-model exact={r['det_round_model']['frac_exact']*100:5.1f}% "
                  f"skew μ={r['skew_pips']['mean']:+.3f}p σ={r['skew_pips']['std']:.3f}p "
                  f"|skew|<=0.5p: {r['skew_pips']['frac_within_half_pip']*100:5.1f}%")
    json.dump(res, open("results/seed1_structure.json", "w"), indent=1)
