"""subpip_leakage.py — does the bid/ask skew leak the sub-pip internal spot?

Model: internal spot S has more precision than the displayed quote q = round(S).
If bid = floor-ish(S*(1-c/2)) and ask = ceil-ish(S*(1+c/2)) then
skew_t = (bid+ask)/2 - q_t ~ S_t - q_t  (the sub-pip fraction, in [-0.5, 0.5] pips).

Prediction if true: E[q_{t+1} - q_t | skew_t] = skew_t + drift, i.e. regression of
next displayed step on skew has slope ~ +1 (in pip units) — testable with small n
because the noise is step sigma, but slope target is exactly 1.

Second-order prediction (digit trading): next-digit PMF should center at
(q_t + skew_t) mod 10, not q_t mod 10. Tested on JD100 via log-loss comparison
once enough live ticks exist.
"""
import json, sys
import numpy as np
from common import load, PIP
from ledger import log_test

def analyze(sym):
    d = load(sym)
    q, sk, ep = d["quote"], d["skew"], d["epoch"]
    # only use consecutive ticks (gap == modal interval)
    iv = np.diff(ep)
    modal = int(np.bincount(iv[iv < 10]).argmax())
    ok = iv == modal
    step = (q[1:] - q[:-1])[ok]
    skew = sk[:-1][ok]
    n = len(step)
    if n < 300 or skew.std() == 0:
        return dict(sym=sym, n=int(n), verdict="skew has zero variance -> no channel")
    # OLS slope of step on skew
    b, a = np.polyfit(skew, step, 1)
    resid = step - (a + b * skew)
    se = resid.std() / (skew.std() * np.sqrt(n))
    t_vs0 = b / se
    t_vs1 = (b - 1.0) / se
    r = float(np.corrcoef(skew, step)[0, 1])
    log_test(instrument=sym, seed=1,
             hypothesis="skew leaks sub-pip spot: slope(step_{t+1} ~ skew_t) > 0",
             stat=f"slope={b:.3f} (target 1.0), r={r:.4f}", n=n, t=float(t_vs0),
             note=f"slope se={se:.3f}; t vs slope=1: {t_vs1:.2f}")
    return dict(sym=sym, n=int(n), slope=float(b), slope_se=float(se),
                t_vs_zero=float(t_vs0), t_vs_one=float(t_vs1), r=r,
                skew_std_pips=float(skew.std()), step_std_pips=float(step.std()))

if __name__ == "__main__":
    syms = sys.argv[1:] or ["CRASH500", "CRASH1000", "BOOM500", "BOOM1000",
                            "JD10", "JD25", "JD50", "JD75", "JD100",
                            "R_100", "1HZ100V", "stpRNG"]
    res = []
    for s in syms:
        try:
            r = analyze(s)
        except FileNotFoundError:
            continue
        res.append(r)
        if "slope" in r:
            print(f"{s:9s} n={r['n']:6d} slope={r['slope']:+7.3f}±{r['slope_se']:.3f} "
                  f"t0={r['t_vs_zero']:+6.2f} t1={r['t_vs_one']:+6.2f} r={r['r']:+.4f} "
                  f"skewσ={r['skew_std_pips']:.3f}p stepσ={r['step_std_pips']:.1f}p")
        else:
            print(f"{s:9s} n={r['n']:6d} {r['verdict']}")
    json.dump(res, open("results/subpip_leakage.json", "w"), indent=1)
