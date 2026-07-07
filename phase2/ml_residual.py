"""ml_residual.py — Phase 2, Axis C.

Residual model on top of the empirical-table PMF (the deployed baseline), NOT a
replacement. A gradient-boosted 10-class model predicts the next digit OFFSET
given microstructure features; the baseline table PMF's log-probs are included
as features so the model only has to learn what the table misses.

Validation (mandate requirements):
  - walk-forward ONLY: expanding train window, forward validation slice
  - purge/embargo gap of W=1800 ticks between train end and validation start
  - headline = incremental log-loss + incremental EV vs the table baseline,
    never standalone accuracy

EV is scored at the EXECUTABLE (authenticated) payout surface (primary) and at
the public surface (secondary, to measure predictive lift independent of the
house edge). Results -> phase2/results/ml_residual.json
"""
import csv, json, math, os, sys, collections

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

HERE = os.path.dirname(os.path.abspath(__file__))
W = 1800
JUMP_THR = 20
PIP = 2
PURGE = 1800

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


def build_dataset():
    tables = {int(k): np.array(v) for k, v in json.load(
        open(os.path.join(HERE, "..", "fable-thoughts", "results",
                          "empirical_offset_tables.json"))).items()}
    path = os.path.join(HERE, "..", "bidask", "data", "JD100.csv")
    ep, q, b, a = [], [], [], []
    with open(path) as f:
        r = csv.reader(f); next(r)
        last = None
        for row in r:
            e = int(row[0])
            if last is not None and e <= last: continue
            last = e
            ep.append(e); q.append(float(row[1])); b.append(float(row[2])); a.append(float(row[3]))
    ep = np.array(ep)
    scale = 10 ** PIP
    v = np.round(np.array(q) * scale).astype(np.int64)
    bid = np.array(b) * scale; ask = np.array(a) * scale
    mid = (bid + ask) / 2
    skew = mid - v          # half-pip position leak (H1, holdout-confirmed)
    spread = ask - bid
    n = len(v)

    sq = collections.deque(maxlen=W); cn = collections.deque(maxlen=W)
    ssq = 0.0; scn = 0
    sqf = collections.deque(maxlen=300); cnf = collections.deque(maxlen=300)
    ssqf = 0.0; scnf = 0
    since_jump = 10**9

    X, y, base_logp, keep_idx = [], [], [], []
    for i in range(1, n - 1):
        st = int(v[i] - v[i - 1])
        nj = 1 if abs(st) <= JUMP_THR else 0
        s2 = float(st * st) if nj else 0.0
        if len(sq) == W: ssq -= sq[0]; scn -= cn[0]
        sq.append(s2); cn.append(nj); ssq += s2; scn += nj
        if len(sqf) == 300: ssqf -= sqf[0]; scnf -= cnf[0]
        sqf.append(s2); cnf.append(nj); ssqf += s2; scnf += nj
        since_jump = 0 if not nj else since_jump + 1
        if scn < 200 or scnf < 150: continue
        sig = math.sqrt(ssq / scn)
        bin_key = int(sig / 0.1)
        if bin_key not in tables: continue
        sigf = math.sqrt(ssqf / scnf)
        d = int(v[i] % 10)
        d1 = int(v[i - 1] % 10)
        dt = float(ep[i] - ep[i - 1]) if i > 0 else 1.0
        hour = (ep[i] % 86400) / 3600.0
        pmf = tables[bin_key]
        off = int((v[i + 1] - v[i]) % 10)   # target: offset of next digit
        feats = [d, d1, (d - d1) % 10, sig, sigf, sigf / max(sig, 1e-9),
                 float(skew[i]), float(spread[i]), dt,
                 math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24),
                 min(since_jump, 5000), float(st)]
        feats += list(np.log(np.maximum(pmf, 1e-9)))
        X.append(feats); y.append(off); base_logp.append(np.log(np.maximum(pmf, 1e-9)))
        keep_idx.append(i)
    return (np.array(X), np.array(y), np.array(base_logp), np.array(keep_idx),
            v, tables)


def ev_score(pmf_rows, digits, next_digits, surface, winmasks, gate=0.01):
    """Trade best-EV contract per tick if EV>gate; realized $1 PnL at executable."""
    pnl, trades = 0.0, 0
    ck_list = list(surface.keys())
    for i in range(len(pmf_rows)):
        pmf = pmf_rows[i]; d = digits[i]
        best_ev, best_ck = gate, None
        for ck in ck_list:
            wm = winmasks[ck]
            p = float(sum(pmf[o] * wm[(d + o) % 10] for o in range(10)))
            ev = p * surface[ck] - 1.0
            if ev > best_ev: best_ev, best_ck = ev, ck
        if best_ck is not None:
            won = next_digits[i] in {j for j in range(10) if winmasks[best_ck][j]}
            pnl += (EXEC[best_ck] - 1.0) if won else -1.0   # settle executable always
            trades += 1
    return pnl, trades


def run():
    global EXEC
    X, y, base_logp, idx, v, tables = build_dataset()
    n = len(y)
    print(f"dataset: {n} rows, {X.shape[1]} features")

    ps = json.load(open(os.path.join(HERE, "results", "payout_surface.json")))
    pub = {k: v_ for k, v_ in ps["public"].items() if v_}
    EXEC = {k: v_ for k, v_ in ps["auth"].items() if v_}
    winmasks = {f"{t}:{b}": np.array([1 if dd in winset(t, b) else 0 for dd in range(10)])
                for t, b in CONTRACTS}

    folds = 5
    bounds = np.linspace(int(n * 0.4), n, folds + 1, dtype=int)
    res = {"folds": [], "n": int(n)}
    tot = collections.defaultdict(float)

    for f in range(folds):
        tr_end = bounds[f] - PURGE
        va_lo, va_hi = bounds[f], bounds[f + 1]
        if tr_end < 5000: continue
        clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.06,
                                             max_depth=6, l2_regularization=1.0,
                                             early_stopping=True, validation_fraction=0.15,
                                             random_state=0)
        clf.fit(X[:tr_end], y[:tr_end])
        P = clf.predict_proba(X[va_lo:va_hi])
        classes = clf.classes_
        Pfull = np.full((va_hi - va_lo, 10), 1e-9)
        for j, c in enumerate(classes): Pfull[:, c] = P[:, j]
        Pfull /= Pfull.sum(1, keepdims=True)

        B = np.exp(base_logp[va_lo:va_hi]); B /= B.sum(1, keepdims=True)
        yv = y[va_lo:va_hi]
        ll_base = -np.mean(np.log(B[np.arange(len(yv)), yv]))
        ll_ml = -np.mean(np.log(np.maximum(Pfull[np.arange(len(yv)), yv], 1e-9)))
        # blended (geometric, w=0.5) — the "residual correction" combination
        C = np.sqrt(B * Pfull); C /= C.sum(1, keepdims=True)
        ll_comb = -np.mean(np.log(np.maximum(C[np.arange(len(yv)), yv], 1e-9)))

        digits = (v[idx[va_lo:va_hi]] % 10).astype(int)
        nxt = (v[idx[va_lo:va_hi] + 1] % 10).astype(int)
        ev = {}
        for name, PM in [("base", B), ("comb", C)]:
            for sname, surf in [("exec", EXEC), ("pub", pub)]:
                pnl, ntr = ev_score(PM, digits, nxt, surf, winmasks)
                ev[f"{name}_{sname}"] = (round(pnl, 2), ntr)
                tot[f"{name}_{sname}_pnl"] += pnl; tot[f"{name}_{sname}_tr"] += ntr
        fold = dict(fold=f, train=int(tr_end), val=[int(va_lo), int(va_hi)],
                    ll_base=round(float(ll_base), 6), ll_ml=round(float(ll_ml), 6),
                    ll_comb=round(float(ll_comb), 6), ev=ev)
        res["folds"].append(fold)
        print(fold)

    res["totals"] = {k: round(vv, 2) for k, vv in tot.items()}
    print("\nTOTALS:", res["totals"])
    json.dump(res, open(os.path.join(HERE, "results", "ml_residual.json"), "w"), indent=1)
    print("saved -> phase2/results/ml_residual.json")


if __name__ == "__main__":
    run()
