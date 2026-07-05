"""collector.py — multi-symbol bid/ask/spot tick collector for the bid-ask lens program.

Subscribes to the public tick stream of the new Deriv API (api.derivws.com) and logs
epoch, quote, bid, ask (exact strings as received) plus local receive time per symbol.

The history endpoint only returns spot prices, so bid/ask MUST be collected live.

Usage: python3 collector.py --outdir data --hours 12
"""
import argparse, json, time, os, csv, signal, sys
import websocket

WS_PUBLIC = "wss://api.derivws.com/trading/v1/options/ws/public"

SYMBOLS = [
    # Volatility family — calibration lab for spread-sigma (Seed 2)
    "R_10", "R_25", "R_50", "R_75", "R_100", "1HZ100V",
    # Crash/Boom — spread-leads-spike (Seed 3), largest amplitude
    "CRASH500", "CRASH1000", "BOOM500", "BOOM1000",
    # Jump family — duty-cycle tradeoff + JD100 baseline
    "JD10", "JD25", "JD50", "JD75", "JD100",
    # Step index — zero-spread curiosity (no digit contracts, reference only)
    "stpRNG",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data")
    ap.add_argument("--hours", type=float, default=12.0)
    ap.add_argument("--symbols", nargs="+", default=SYMBOLS)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    files, writers = {}, {}
    for s in a.symbols:
        path = os.path.join(a.outdir, f"{s}.csv")
        new = not os.path.exists(path) or os.path.getsize(path) == 0
        f = open(path, "a", newline="")
        w = csv.writer(f)
        if new:
            w.writerow(["epoch", "quote", "bid", "ask", "recv_ts"])
        files[s], writers[s] = f, w

    def cleanup(*_):
        for f in files.values():
            try: f.flush(); f.close()
            except Exception: pass
        sys.exit(0)
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    t_end = time.time() + a.hours * 3600
    n = {s: 0 for s in a.symbols}
    last_flush = time.time()
    ws = None
    while time.time() < t_end:
        try:
            if ws is None:
                ws = websocket.create_connection(WS_PUBLIC, timeout=30)
                for s in a.symbols:
                    ws.send(json.dumps({"ticks": s, "subscribe": 1}))
                print(time.strftime("%H:%M:%S"), "connected,", len(a.symbols), "subs", flush=True)
            m = json.loads(ws.recv())
        except Exception as e:
            print(time.strftime("%H:%M:%S"), "reconnect:", repr(e)[:120], flush=True)
            try: ws.close()
            except Exception: pass
            ws = None
            time.sleep(2)
            continue
        if m.get("msg_type") != "tick" or "tick" not in m:
            continue
        t = m["tick"]
        s = t["symbol"]
        if s not in writers:
            continue
        # repr() keeps exact JSON float; format via repr to avoid precision loss
        writers[s].writerow([t["epoch"], repr(t["quote"]), repr(t["bid"]), repr(t["ask"]),
                             f"{time.time():.3f}"])
        n[s] += 1
        if time.time() - last_flush > 15:
            for f in files.values(): f.flush()
            last_flush = time.time()
            total = sum(n.values())
            if total and int(last_flush) % 600 < 20:
                print(time.strftime("%H:%M:%S"), "counts", n, flush=True)
    cleanup()


if __name__ == "__main__":
    main()
