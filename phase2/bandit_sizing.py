"""bandit_sizing.py — Phase 2, Axis A.

Contextual-bandit sizing layer replacing fixed-fraction Kelly, backtested
walk-forward on the JD100 bid/ask tick corpus (sessions 1-3).

Arms: (sigma_bin, contract). Each arm keeps a Beta posterior over its true win
probability, seeded softly from the Phase-1 empirical offset tables (pseudo-n
configurable) and updated from every observed tick outcome (digit outcomes are
public information — full-information updates, exactly as available live).

Stake rule ("wide posterior -> small stake"): stake = base * Kelly fraction
evaluated at a conservative posterior quantile (LCB), floored at 0. EV is ALWAYS
computed against the EXECUTABLE (authenticated) payout surface (Phase-1 rule).

Policies compared, identical tick stream, walk-forward, no look-ahead:
  P0 static-public : fixed $1, gate EV>1% at PUBLIC payouts (the Phase-1
                     disaster, for reference — what sentinel_v2 actually did)
  P1 static-kelly  : half-Kelly at table p and PUBLIC payouts, same gate
  P2 honest-static : fixed $1, gate EV>1% at EXECUTABLE payouts (patched
                     sentinel — expected to never trade)
  P3 bandit        : Thompson/LCB-Kelly at EXECUTABLE payouts, posterior-live
  P4 bandit-public : the bandit but PRICED at public payouts (isolates: does
                     the live posterior alone rescue you from a wrong payout?)

The single number: total realized PnL per policy on the same out-of-sample
stream. Results -> phase2/results/bandit_backtest.json
"""
import json, math, os, sys, collections

import numpy as np
from scipy.stats import beta as beta_dist

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bidask"))

W = 1800
JUMP_THR = 20
PIP = 2  # JD100

CONTRACTS = ([("DIGITMATCH", d) for d in range(10)] + [("DIGITDIFF", d) for d in range(10)] +
             [("DIGITOVER", k) for k in range(9)] + [("DIGITUNDER", k) for k in range(1, 10)] +
             [("DIGITEVEN", None), ("DIGITODD", None)])


def winset(t, b):
    if t == "DIGITMATCH": return {b}
    if t == "DIGITDIFF": return set(range(10)) - {b}
    if t == "DIGITOVER": return set(range(b + 1, 10))
    if t == "DIGITUNDER": return set(range(0, b))
    if t == "DIGITEVEN": return {0, 2, 4, 6, 8}
    return {1, 3, 5, 7, 9}


def load_surfaces():
    ps = json.load(open(os.path.join(HERE, "results", "payout_surface.json")))
    pub = {k: v for k, v in ps["public"].items() if v}
    auth = {k: v for k, v in ps["auth"].items() if v}
    return pub, auth


def load_tables():
    raw = json.load(open(os.path.join(HERE, "..", "fable-thoughts", "results",
                                      "empirical_offset_tables.json")))
    return {int(k): np.array(v) for k, v in raw.items()}


def load_quotes():
    import csv
    path = os.path.join(HERE, "..", "bidask", "data", "JD100.csv")
    ep, q = [], []
    with open(path) as f:
        r = csv.reader(f); next(r)
        last = None
        for row in r:
            e = int(row[0])
            if last is not None and e <= last: continue
            last = e
            ep.append(e); q.append(float(row[1]))
    return np.array(ep), np.array(q)


def kelly(p, M):
    """Kelly fraction for binary bet paying M per unit stake (M includes stake)."""
    b = M - 1.0
    if b <= 0: return 0.0
    return max(0.0, (p * M - 1.0) / b)


class Arm:
    __slots__ = ("a", "b")
    def __init__(self, p0, pseudo_n):
        self.a = p0 * pseudo_n
        self.b = (1 - p0) * pseudo_n
    def update(self, won):
        if won: self.a += 1
        else: self.b += 1
    def lcb(self, q=0.2):
        return beta_dist.ppf(q, self.a, self.b)
    def mean(self):
        return self.a / (self.a + self.b)


def run():
    tables = load_tables()
    pub, auth = load_surfaces()
    ep, quotes = load_quotes()
    v = np.round(quotes * 10**PIP).astype(np.int64)
    n = len(v)
    print(f"{n} JD100 ticks loaded")

    ckeys = [f"{t}:{b}" for t, b in CONTRACTS]
    winsets = {f"{t}:{b}": winset(t, b) for t, b in CONTRACTS}
    winmask = {k: np.array([1 if d in winsets[k] else 0 for d in range(10)]) for k in ckeys}

    # table p per (bin, digit, contract): computed lazily
    pcache = {}
    def table_p(bin_key, digit, ck):
        key = (bin_key, digit, ck)
        if key not in pcache:
            pmf = tables[bin_key]
            wm = winmask[ck]
            pcache[key] = float(sum(pmf[off] * wm[(digit + off) % 10] for off in range(10)))
        return pcache[key]

    GATE = 0.01
    SIGMA_MAX = 4.35
    PSEUDO_N = 200.0
    LCB_Q = 0.2
    BASE = 25.0   # max stake scale for kelly policies (fraction applied to this)

    arms = {}           # P3: priced at auth
    def get_arm(bin_key, digit, ck):
        key = (bin_key, digit, ck)
        if key not in arms:
            arms[key] = Arm(table_p(bin_key, digit, ck), PSEUDO_N)
        return arms[key]

    pnl = {k: 0.0 for k in ["P0", "P1", "P2", "P3", "P4"]}
    trades = {k: 0 for k in pnl}
    staked = {k: 0.0 for k in pnl}
    curves = {k: [] for k in pnl}

    # rolling sigma state
    sq = collections.deque(maxlen=W); cn = collections.deque(maxlen=W)
    ssq = 0.0; scn = 0

    checkpoints = set(np.linspace(0, n - 1, 25, dtype=int).tolist())

    for i in range(1, n - 1):
        st = v[i] - v[i - 1]
        nj = 1 if abs(st) <= JUMP_THR else 0
        s2 = float(st * st) if nj else 0.0
        if len(sq) == W:
            ssq -= sq[0]; scn -= cn[0]
        sq.append(s2); cn.append(nj); ssq += s2; scn += nj
        if scn < 200: continue
        sig = math.sqrt(ssq / scn)
        bin_key = int(sig / 0.1)
        if bin_key not in tables: continue

        digit = v[i] % 10
        nxt = v[i + 1] % 10

        # candidate selection: best contract by believed EV per policy
        best = {}
        for ck in ckeys:
            p = table_p(bin_key, digit, ck)
            if ck in pub:
                evp = p * pub[ck] - 1.0
                if evp > best.get("P0", (GATE, None))[0]:
                    best["P0"] = (evp, ck, p)
            if ck in auth:
                eva = p * auth[ck] - 1.0
                if eva > best.get("P2", (GATE, None))[0]:
                    best["P2"] = (eva, ck, p)

        gate_open = sig <= SIGMA_MAX

        # P0 static-public fixed $1
        if gate_open and "P0" in best:
            _, ck, p = best["P0"]
            won = nxt in winsets[ck]
            pnl["P0"] += (auth[ck] - 1.0) if won else -1.0   # settles at EXECUTABLE
            trades["P0"] += 1; staked["P0"] += 1.0

        # P1 static half-Kelly at public
        if gate_open and "P0" in best:
            _, ck, p = best["P0"]
            f = 0.5 * kelly(p, pub[ck])
            stake = BASE * f
            if stake > 0.01:
                won = nxt in winsets[ck]
                pnl["P1"] += stake * ((auth[ck] - 1.0) if won else -1.0)
                trades["P1"] += 1; staked["P1"] += stake

        # P2 honest static fixed $1
        if gate_open and "P2" in best:
            _, ck, p = best["P2"]
            won = nxt in winsets[ck]
            pnl["P2"] += (auth[ck] - 1.0) if won else -1.0
            trades["P2"] += 1; staked["P2"] += 1.0

        # P3 bandit at executable payouts: LCB-Kelly stake
        # pick arm with best LCB EV among top-3 candidates by table EV (cheap)
        cand = sorted(ckeys, key=lambda ck: -(table_p(bin_key, digit, ck) * auth.get(ck, 0)))[:3]
        if gate_open:
            for ck in cand:
                if ck not in auth: continue
                arm = get_arm(bin_key, digit, ck)
                plcb = arm.lcb(LCB_Q)
                ev_lcb = plcb * auth[ck] - 1.0
                if ev_lcb > GATE:
                    stake = BASE * kelly(plcb, auth[ck])
                    if stake > 0.01:
                        won = nxt in winsets[ck]
                        pnl["P3"] += stake * ((auth[ck] - 1.0) if won else -1.0)
                        trades["P3"] += 1; staked["P3"] += stake
                    break

        # P4 bandit priced at PUBLIC payouts (belief), settling executable
        if gate_open:
            for ck in cand:
                if ck not in pub or ck not in auth: continue
                arm = get_arm(bin_key, digit, ck)   # shared posterior (win prob is same)
                plcb = arm.lcb(LCB_Q)
                ev_lcb = plcb * pub[ck] - 1.0
                if ev_lcb > GATE:
                    stake = BASE * kelly(plcb, pub[ck])
                    if stake > 0.01:
                        won = nxt in winsets[ck]
                        pnl["P4"] += stake * ((auth[ck] - 1.0) if won else -1.0)
                        trades["P4"] += 1; staked["P4"] += stake
                    break

        # full-information posterior updates: every candidate arm sees the outcome
        for ck in cand:
            get_arm(bin_key, digit, ck).update(nxt in winsets[ck])

        if i in checkpoints:
            for k in pnl: curves[k].append(round(pnl[k], 2))

    print(f"\n{'policy':<14}{'trades':>8}{'staked':>10}{'pnl':>10}{'pnl/$staked':>12}")
    for k in ["P0", "P1", "P2", "P3", "P4"]:
        r = pnl[k] / staked[k] if staked[k] else 0.0
        print(f"{k:<14}{trades[k]:>8}{staked[k]:>10.2f}{pnl[k]:>10.2f}{r*100:>11.2f}%")

    out = dict(n_ticks=int(n), pnl=pnl, trades=trades, staked=staked, curves=curves,
               params=dict(GATE=GATE, SIGMA_MAX=SIGMA_MAX, PSEUDO_N=PSEUDO_N,
                           LCB_Q=LCB_Q, BASE=BASE))
    json.dump(out, open(os.path.join(HERE, "results", "bandit_backtest.json"), "w"), indent=1)
    print("saved -> phase2/results/bandit_backtest.json")


if __name__ == "__main__":
    run()
