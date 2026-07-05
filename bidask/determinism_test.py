"""determinism_test.py — THE killer test for the whole bid/ask lens.

If ask == round(quote*(1+c/2)) and bid == round(quote*(1-c/2)) for a per-symbol
constant c, then bid/ask carry ZERO bits beyond spot, and every downstream seed
(spread-sigma, spread-leads-spike, skew) is a statement about ROUNDING, not markets.

For each symbol: fit c = mean(spread/quote), then scan a fine grid around it
minimizing exact-match failures of BOTH sides. Report best exact-match rate and
the distribution of residuals (in pips) for ask and bid separately.
"""
import json, sys
import numpy as np
from common import load, PIP
from ledger import log_test

def analyze(sym):
    d = load(sym)
    q, b, a = d["quote"], d["bid"], d["ask"]
    n = len(q)
    if n < 500:
        return None
    c0 = float(np.mean((a - b) / q))
    best = None
    for c in np.linspace(c0 * 0.98, c0 * 1.02, 401):
        h = c / 2 * q
        # try both round-half-even (numpy) and floor/ceil conventions
        for name, fa, fb in (("round", np.round(q + h) - q, q - np.round(q - h)),
                             ("ceilask", np.ceil(q + h - 1e-9) - q, q - np.floor(q - h + 1e-9))):
            ra = a - q - fa   # ask residual in pips
            rb = q - b - fb   # bid residual
            exact = float(np.mean((np.abs(ra) < 1e-6) & (np.abs(rb) < 1e-6)))
            if best is None or exact > best[0]:
                best = (exact, c, name, ra, rb)
    exact, c, conv, ra, rb = best
    within1 = float(np.mean((np.abs(ra) <= 1.000001) & (np.abs(rb) <= 1.000001)))
    out = dict(sym=sym, n=int(n), c_bps=float(c * 1e4), convention=conv,
               exact_match=exact, within_1pip=within1,
               ask_resid_std=float(ra.std()), bid_resid_std=float(rb.std()),
               ask_resid_max=float(np.abs(ra).max()), bid_resid_max=float(np.abs(rb).max()))
    log_test(instrument=sym, seed=1,
             hypothesis="bid/ask deterministic function of spot (round(c*q) model)",
             stat=f"exact={exact*100:.1f}% within1pip={within1*100:.1f}%", n=n,
             p=None, note=f"c={c*1e4:.4f}bps conv={conv}; descriptive, no p-value")
    return out

if __name__ == "__main__":
    syms = sys.argv[1:] or ["CRASH500", "CRASH1000", "BOOM500", "BOOM1000",
                            "JD10", "JD25", "JD50", "JD75", "JD100",
                            "R_100", "1HZ100V"]
    res = []
    for s in syms:
        try:
            r = analyze(s)
        except FileNotFoundError:
            continue
        if r:
            res.append(r)
            print(f"{s:9s} n={r['n']:6d} c={r['c_bps']:.4f}bps conv={r['convention']:8s} "
                  f"exact={r['exact_match']*100:5.1f}% within1pip={r['within_1pip']*100:5.1f}% "
                  f"resid_std ask={r['ask_resid_std']:.3f} bid={r['bid_resid_std']:.3f} "
                  f"max ask={r['ask_resid_max']:.1f} bid={r['bid_resid_max']:.1f}")
    json.dump(res, open("results/determinism_test.json", "w"), indent=1)
