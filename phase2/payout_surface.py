"""payout_surface.py — Phase 2, Hours 0-2.

Re-verify the CURRENT authenticated (executable) payout surface across all 40
JD100 digit contracts, side by side with the public-socket quote, and answer:
does ANY contract clear its true breakeven at the model's best conditional
probability (max over sigma bins x current digits, empirical offset tables)?

First-class permanent rule (Phase 1 finding): no EV is ever computed from the
public socket. Executable payout = authenticated proposal, verified fresh.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bidask"))
from deriv_api import DerivWS

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


def probe_surface(conn, sym="JD100", stake=1.0, sleep=0.08):
    out = {}
    for t, b in CONTRACTS:
        req = dict(amount=stake, basis="stake", contract_type=t, currency="USD",
                   duration=1, duration_unit="t", underlying_symbol=sym)
        if b is not None:
            req["barrier"] = str(b)
        r = conn.proposal(**req)
        if "proposal" in r:
            out[f"{t}:{b}"] = float(r["proposal"]["payout"]) / stake
        else:
            out[f"{t}:{b}"] = None
        time.sleep(sleep)
    return out


def best_model_p(tables):
    """For each contract, max over (sigma_bin, current_digit) of P(win)."""
    best = {}
    for t, b in CONTRACTS:
        ws_ = winset(t, b)
        m, arg = 0.0, None
        for bin_key, pmf in tables.items():
            for d in range(10):
                p = sum(pmf[off] for off in range(10) if (d + off) % 10 in ws_)
                if p > m:
                    m, arg = p, (bin_key, d)
        best[f"{t}:{b}"] = {"p": m, "at": arg}
    return best


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    tables = json.load(open(os.path.join(here, "..", "fable-thoughts", "results",
                                         "empirical_offset_tables.json")))
    pub = DerivWS(token="")
    auth = DerivWS()
    print("probing public surface...")
    P = probe_surface(pub)
    print("probing authenticated surface...")
    A = probe_surface(auth)
    B = best_model_p(tables)

    rows, any_positive = [], []
    for t, b in CONTRACTS:
        k = f"{t}:{b}"
        pu, au = P[k], A[k]
        bp = B[k]["p"]
        if au:
            be = 1.0 / au
            ev = bp * au - 1.0
            rows.append((k, pu, au, be, bp, ev, B[k]["at"]))
            if ev > 0:
                any_positive.append((k, ev, B[k]["at"]))
    rows.sort(key=lambda r: -r[5])
    print(f"\n{'contract':<16}{'public':>8}{'auth':>8}{'brkevn':>8}{'bestp':>8}{'maxEV%':>8}  at")
    for k, pu, au, be, bp, ev, at in rows:
        print(f"{k:<16}{pu or 0:>8.3f}{au:>8.3f}{be:>8.4f}{bp:>8.4f}{ev*100:>8.2f}  {at}")
    print(f"\ncontracts with positive best-case EV at executable payout: {len(any_positive)}")
    for k, ev, at in any_positive:
        print(f"  {k}: +{ev*100:.2f}% at bin/digit {at}")

    res = {"ts": time.time(), "public": P, "auth": A,
           "best_model_p": {k: v for k, v in B.items()},
           "positive": any_positive}
    out = os.path.join(here, "results")
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, "payout_surface.json"), "w"), indent=1)
    print("\nsaved -> phase2/results/payout_surface.json")
    pub.close(); auth.close()


if __name__ == "__main__":
    main()
