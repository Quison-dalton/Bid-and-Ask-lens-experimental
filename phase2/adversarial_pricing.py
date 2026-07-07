"""adversarial_pricing.py — Phase 2, Axis B.

Does Deriv's executable (authenticated) payout respond to the account's own
trading history — winning streaks vs losing streaks?

Design (single demo account -> within-account block design):
  cycle = [probe surface] -> 25x DIGITDIFF:0 trades (p_win ~0.9, "winning
  streak" arm) -> [probe] -> 25x DIGITMATCH:0 trades (p_win ~0.1, "losing
  streak" arm) -> [probe] -> sleep gap
Repeated for --cycles. Every probe is authenticated + fresh (Phase 1 rule),
covers 6 sentinel contracts, and records the account balance.

If payouts drift measurably after high-win blocks vs low-win blocks, pricing
is responsive; if flat everywhere, pricing is static at account level.
Everything logged to phase2/results/adversarial_log.jsonl (one event per line).
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bidask"))
from deriv_api import DerivWS

PROBE_SET = [("DIGITOVER", 5), ("DIGITUNDER", 4), ("DIGITEVEN", None),
             ("DIGITODD", None), ("DIGITMATCH", 0), ("DIGITDIFF", 0)]
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "adversarial_log.jsonl")


def log(ev):
    ev["ts"] = time.time()
    with open(LOG, "a") as f:
        f.write(json.dumps(ev) + "\n")


def probe(conn, sym="JD100", stake=1.0):
    out = {}
    for t, b in PROBE_SET:
        req = dict(amount=stake, basis="stake", contract_type=t, currency="USD",
                   duration=1, duration_unit="t", underlying_symbol=sym)
        if b is not None:
            req["barrier"] = str(b)
        r = conn.proposal(**req)
        out[f"{t}:{b}"] = float(r["proposal"]["payout"]) / stake if "proposal" in r else None
        time.sleep(0.1)
    bal = conn.call({"balance": 1}).get("balance", {}).get("balance")
    return out, bal


def trade_block(conn, ctype, barrier, n, sym="JD100", stake=1.0):
    """Fire n 1-tick trades sequentially, waiting for settlement of each."""
    wins = losses = 0
    pnl = 0.0
    for i in range(n):
        try:
            req = dict(amount=stake, basis="stake", contract_type=ctype, currency="USD",
                       duration=1, duration_unit="t", underlying_symbol=sym)
            if barrier is not None:
                req["barrier"] = str(barrier)
            pr = conn.proposal(**req)
            if "proposal" not in pr:
                log({"ev": "proposal_fail", "err": pr.get("error", {}).get("message")})
                time.sleep(2); continue
            pid = pr["proposal"]["id"]
            ask = float(pr["proposal"]["ask_price"])
            payout = float(pr["proposal"]["payout"])
            br = conn.buy(pid, ask * 1.02)
            if "buy" not in br:
                log({"ev": "buy_fail", "err": br.get("error", {}).get("message")})
                time.sleep(2); continue
            cid = br["buy"]["contract_id"]
            buy_price = float(br["buy"]["buy_price"])
            # poll settlement
            profit = None
            for _ in range(30):
                time.sleep(1.0)
                oc = conn.open_contract(cid)
                c = oc.get("proposal_open_contract", {})
                if c.get("is_sold") or c.get("status") in ("won", "lost"):
                    profit = float(c.get("profit", 0.0))
                    break
            if profit is None:
                log({"ev": "settle_timeout", "cid": cid}); continue
            pnl += profit
            if profit > 0: wins += 1
            else: losses += 1
            log({"ev": "trade", "arm": f"{ctype}:{barrier}", "i": i, "cid": cid,
                 "buy": buy_price, "payout_q": payout, "profit": profit})
        except Exception as e:
            log({"ev": "trade_err", "err": str(e)})
            time.sleep(3)
    return wins, losses, pnl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=8)
    ap.add_argument("--block", type=int, default=25)
    ap.add_argument("--gap-min", type=float, default=12.0)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(LOG), exist_ok=True)

    conn = DerivWS()
    log({"ev": "start", "account": conn.account.get("account_id"), "cycles": a.cycles})
    s, bal = probe(conn)
    log({"ev": "probe", "phase": "baseline", "surface": s, "balance": bal})
    print(f"baseline: {s} bal={bal}", flush=True)

    for c in range(a.cycles):
        for arm, ctype, barrier in [("HIGHWIN", "DIGITDIFF", 0), ("LOWWIN", "DIGITMATCH", 0)]:
            try:
                w, l, pnl = trade_block(conn, ctype, barrier, a.block)
            except Exception as e:
                log({"ev": "block_err", "err": str(e)})
                try:
                    conn.close()
                except Exception:
                    pass
                conn = DerivWS()
                w, l, pnl = trade_block(conn, ctype, barrier, a.block)
            s, bal = probe(conn)
            log({"ev": "probe", "phase": f"cycle{c}_{arm}", "wins": w, "losses": l,
                 "pnl": pnl, "surface": s, "balance": bal})
            print(f"cycle {c} {arm}: {w}W/{l}L pnl={pnl:+.2f} bal={bal} surface={s}", flush=True)
        time.sleep(a.gap_min * 60)
    log({"ev": "done"})
    print("done", flush=True)


if __name__ == "__main__":
    main()
