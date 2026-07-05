"""seed3_event_study.py — Seed 3: does the spread (or skew) widen BEFORE a move?

The market-maker hypothesis: if Deriv's generator behaves like a market maker, it
widens quotes ahead of engineered spikes. Crash/Boom is the loudest place to test
(spikes are the designed feature); JD jumps second.

Events:
 - CRASH*: down-spike = step < -8 * median|step| ; BOOM*: up-spike mirrored.
 - JD*:    |step| > 6 MAD-sigma (same as rolling_sigma jump threshold).

Test: mean spread-residual and mean |skew| over pre-event windows [-W..-1] vs
random-placement permutation distribution (block permutation, 2000 draws).
Also a lag profile: mean spread-residual at each single lag -30..+10.
"""
import json, sys
import numpy as np
from common import load, block_perm_pvalue
from ledger import log_test

PRE = 30

def events_for(sym, q):
    st = np.diff(q)
    med = np.median(np.abs(st)) or 1.0
    if sym.startswith("CRASH"):
        idx = np.where(st < -8 * med)[0]
    elif sym.startswith("BOOM"):
        idx = np.where(st > 8 * med)[0]
    else:
        mad = np.median(np.abs(st - np.median(st))) or 1.0
        idx = np.where(np.abs(st) > 6 * 1.4826 * mad)[0]
    # de-cluster: keep events at least PRE apart
    keep = []
    for i in idx:
        if not keep or i - keep[-1] > PRE:
            keep.append(int(i))
    return [i for i in keep if i >= PRE + 1]

def pre_mean(series, ev, pre):
    vals = []
    for i in ev:
        w = series[i - pre:i]
        if len(w) == pre:
            vals.append(np.nanmean(w))
    return float(np.nanmean(vals)) if vals else float("nan")

def analyze(sym):
    d = load(sym)
    q, sp, sk = d["quote"], d["spread"], d["skew"]
    if len(q) < 2000:
        return None
    b, a = np.polyfit(q, sp, 1)
    spr = (sp - (a + b * q))[1:]     # aligned with step index: spr[i] = spread at tick i+1... 
    spr_pre = (sp - (a + b * q))[:-1]  # spread AT tick i (before step i -> i+1)
    skew_pre = np.abs(sk[:-1])
    ev = events_for(sym, q)
    if len(ev) < 5:
        return dict(sym=sym, n=int(len(q)), n_events=len(ev), verdict="too few events")
    # main tests: pre-event mean vs permutation
    obs_sp, p_sp = block_perm_pvalue(spr_pre, ev, PRE, pre_mean)
    obs_sk, p_sk = block_perm_pvalue(skew_pre, ev, PRE, pre_mean)
    base_sp = float(np.nanmean(spr_pre)); base_sk = float(np.nanmean(skew_pre))
    # lag profile of raw spread residual around events
    prof = {}
    for lag in range(-PRE, 11):
        vals = [spr_pre[i + lag] for i in ev if 0 <= i + lag < len(spr_pre)]
        prof[lag] = float(np.nanmean(vals))
    log_test(instrument=sym, seed=3, hypothesis=f"pre-spike spread widening (window {PRE})",
             stat=f"pre={obs_sp:.4f}p vs base={base_sp:.4f}p", n=len(ev), p=p_sp,
             note="block permutation, 2000 draws")
    log_test(instrument=sym, seed=3, hypothesis=f"pre-spike |skew| elevation (window {PRE})",
             stat=f"pre={obs_sk:.4f}p vs base={base_sk:.4f}p", n=len(ev), p=p_sk,
             note="block permutation, 2000 draws")
    return dict(sym=sym, n=int(len(q)), n_events=len(ev),
                pre_spread_resid=obs_sp, base_spread_resid=base_sp, p_spread=p_sp,
                pre_abs_skew=obs_sk, base_abs_skew=base_sk, p_skew=p_sk,
                lag_profile=prof)

if __name__ == "__main__":
    syms = sys.argv[1:] or ["CRASH500", "CRASH1000", "BOOM500", "BOOM1000",
                            "JD10", "JD25", "JD50", "JD75", "JD100"]
    res = []
    for s in syms:
        try:
            r = analyze(s)
        except FileNotFoundError:
            continue
        if r:
            res.append(r)
            if "p_spread" in r:
                print(f"{s:9s} n={r['n']:6d} events={r['n_events']:3d} "
                      f"preSpr={r['pre_spread_resid']:+.4f}p (base {r['base_spread_resid']:+.4f}) p={r['p_spread']:.3f} | "
                      f"pre|skew|={r['pre_abs_skew']:.4f}p (base {r['base_abs_skew']:.4f}) p={r['p_skew']:.3f}")
            else:
                print(f"{s:9s} n={r['n']:6d} events={r['n_events']:3d} {r['verdict']}")
    json.dump(res, open("results/seed3_event_study.json", "w"), indent=1)
