"""ledger.py — central hypothesis ledger across ALL instruments and seeds.

Every statistical test run this session gets logged here. The final correction
(Benjamini-Hochberg FDR) is computed against the COMBINED set, per the addendum's
compounded-multiple-testing requirement.
"""
import json, os, time, math

PATH = os.path.join(os.path.dirname(__file__), "results", "hypothesis_ledger.json")


def _load():
    try:
        return json.load(open(PATH))
    except Exception:
        return []


def log_test(instrument, seed, hypothesis, stat, n, t=None, p=None, note=""):
    L = _load()
    if p is None and t is not None:
        # two-sided normal approx
        p = math.erfc(abs(t) / math.sqrt(2))
    key = (instrument, seed, hypothesis)
    L = [e for e in L if (e["instrument"], e["seed"], e["hypothesis"]) != key]
    L.append(dict(instrument=instrument, seed=seed, hypothesis=hypothesis, stat=stat,
                  n=int(n), t=None if t is None else float(t),
                  p=None if p is None else float(p), note=note,
                  ts=time.strftime("%Y-%m-%d %H:%M:%S")))
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    json.dump(L, open(PATH, "w"), indent=1)


def bh_fdr(alpha=0.05):
    """Benjamini-Hochberg over the combined ledger. Returns entries that survive."""
    L = [e for e in _load() if e.get("p") is not None]
    L.sort(key=lambda e: e["p"])
    m = len(L)
    surv_idx = -1
    for i, e in enumerate(L):
        if e["p"] <= (i + 1) / m * alpha:
            surv_idx = i
    return L, L[:surv_idx + 1] if surv_idx >= 0 else []


if __name__ == "__main__":
    L, surv = bh_fdr()
    print(f"ledger: {len(L)} tests with p-values; BH-FDR(0.05) survivors: {len(surv)}")
    for e in L:
        mark = " *SURVIVES*" if e in surv else ""
        print(f"  p={e['p']:.2e} t={e['t'] and round(e['t'],2)} n={e['n']:7d} "
              f"[{e['instrument']} seed{e['seed']}] {e['hypothesis']}{mark}")
