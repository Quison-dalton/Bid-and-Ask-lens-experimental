"""jd_duty_cycle.py — the addendum's duty-cycle tradeoff, quantified on deep history.

For each JD symbol (250k ticks ≈ 2.9 days):
 - rolling sigma with the SAME estimator family as sentinel_v2 (W=1800, jump thr from MAD)
 - jump rate per hour
 - fraction of time "tradeable" under a sigma stability criterion
 - edge proxy: per-tick best digit EV from the wrapped-normal PMF at the static payout
   grid (sigma_model.GRID), evaluated at each tick's sigma/digit. This is the same
   physics sentinel_v2 falls back to when no empirical table exists — an EDGE PROXY,
   not a validated edge (empirical tables exist only for JD100).
 - expected daily EV proxy = mean(max(best EV,0) over ticks) x ticks/day.
"""
import gzip, json, math, sys, collections
import numpy as np
sys.path.insert(0, "../fable-thoughts/tools")
from sigma_model import wrapped_normal_pmf, winset, CONTRACTS, GRID

W = 1800

def analyze(sym, gate=0.01):
    with gzip.open(f"data/{sym}_hist.json.gz", "rt") as f:
        h = json.load(f)
    pip = int(h["pip"])
    v = np.round(np.array(h["prices"], dtype=float) * 10 ** pip).astype(np.int64)
    times = np.array(h["times"])
    st = np.diff(v)
    mad = np.median(np.abs(st - np.median(st))) or 1.0
    thr = max(20.0, 6 * 1.4826 * mad)  # JD100 uses 20 pips; scale others by MAD but keep >=20
    nj = np.abs(st) <= thr
    jumps_per_hour = float((~nj).sum() / ((times[-1] - times[0]) / 3600))
    sq = np.where(nj, (st.astype(float)) ** 2, 0.0)
    cn = nj.astype(float)
    csq = np.concatenate([[0.0], np.cumsum(sq)]); ccn = np.concatenate([[0.0], np.cumsum(cn)])
    sig = np.full(len(st), np.nan)
    for i in range(W, len(st) + 1):
        n = ccn[i] - ccn[i - W]
        if n >= 200:
            sig[i - 1] = math.sqrt((csq[i] - csq[i - W]) / n)
    digits = (v[1:] % 10)
    # per-tick best EV from wrapped-normal at 0.05-sigma cache resolution
    cache = {}
    best_ev = np.full(len(st), np.nan)
    for i in range(len(st)):
        s = sig[i]
        if not np.isfinite(s):
            continue
        key = (round(s / 0.05), int(digits[i]))
        if key not in cache:
            pmf = wrapped_normal_pmf(max(0.3, key[0] * 0.05), key[1])
            b = max(sum(pmf[x] for x in winset(t, bb)) * M - 1 for (t, bb), M in GRID.items())
            cache[key] = b
        best_ev[i] = cache[key]
    m = np.isfinite(best_ev)
    frac_signal = float(np.mean(best_ev[m] > gate))
    mean_ev_when_signal = float(np.mean(best_ev[m][best_ev[m] > gate])) if frac_signal else 0.0
    tick_iv = float(np.median(np.diff(times)))
    ticks_day = 86400 / tick_iv
    daily_ev_proxy = mean_ev_when_signal * frac_signal * ticks_day  # per $1 staked each signal
    return dict(sym=sym, n=len(v), pip=pip, jump_thr_pips=float(thr),
                jumps_per_hour=jumps_per_hour, tick_interval_s=tick_iv,
                sigma_med=float(np.nanmedian(sig)), sigma_p10=float(np.nanpercentile(sig, 10)),
                sigma_p90=float(np.nanpercentile(sig, 90)),
                frac_ticks_signal=frac_signal, mean_ev_when_signal=mean_ev_when_signal,
                daily_ev_proxy_per_$1=daily_ev_proxy)

if __name__ == "__main__":
    res = []
    for sym in (sys.argv[1:] or ["JD10", "JD25", "JD50", "JD75", "JD100"]):
        try:
            r = analyze(sym)
        except FileNotFoundError:
            print(sym, "no history"); continue
        res.append(r)
        print(f"{sym:6s} n={r['n']} thr={r['jump_thr_pips']:.0f}p jumps/h={r['jumps_per_hour']:.1f} "
              f"σ med={r['sigma_med']:.2f} [{r['sigma_p10']:.2f}..{r['sigma_p90']:.2f}] "
              f"signal%={r['frac_ticks_signal']*100:.1f} evWhen={r['mean_ev_when_signal']*100:+.2f}% "
              f"dailyEVproxy=${r['daily_ev_proxy_per_$1']:.1f}/[$1 stakes]")
    json.dump(res, open("results/jd_duty_cycle.json", "w"), indent=1)
