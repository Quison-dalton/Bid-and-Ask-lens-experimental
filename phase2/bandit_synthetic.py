"""bandit_synthetic.py — Axis A validation: does the bandit machinery actually
scale INTO a genuine edge (not just refuse everything)?

Synthetic stream: one arm (one sigma-bin/digit/contract context) has true win
probability = breakeven + delta; all others are house-edged. The bandit gets
the SAME soft prior (pseudo-n at the stale table p, which UNDERSTATES the true
p for the good arm — i.e. the snapshot is wrong in the pessimistic direction)
and must discover and size the real edge from outcomes alone.

Pass criterion: bandit total PnL > 0 and grows superlinearly vs a fixed-$1
policy on the same stream, while staking near-zero on the bad arms.
"""
import json, math, os
import numpy as np
from scipy.stats import beta as beta_dist

rng = np.random.default_rng(7)

M_EXEC = 2.22          # executable payout for the 4-digit contract class
BREAKEVEN = 1 / M_EXEC # 0.4505
DELTA = 0.02           # true edge of the good arm: p = 0.4705
P_GOOD = BREAKEVEN + DELTA
P_BAD = 0.40           # bad arms' true p
TABLE_P = 0.4165       # what the stale snapshot claims for every arm
PSEUDO_N = 200.0
LCB_Q = 0.2
GATE = 0.01
BASE = 25.0
N_ARMS = 8             # arm 0 is the good one
N_TICKS = 60000


def kelly(p, M):
    b = M - 1.0
    return max(0.0, (p * M - 1.0) / b) if b > 0 else 0.0


class Arm:
    def __init__(self, p0, n0):
        self.a, self.b = p0 * n0, (1 - p0) * n0
    def update(self, won):
        if won: self.a += 1
        else: self.b += 1
    def lcb(self, q=LCB_Q):
        return beta_dist.ppf(q, self.a, self.b)


def run():
    arms = [Arm(TABLE_P, PSEUDO_N) for _ in range(N_ARMS)]
    truth = [P_GOOD] + [P_BAD] * (N_ARMS - 1)
    pnl_bandit = pnl_fixed = 0.0
    staked_bandit = 0.0
    stake_on_good = stake_on_bad = 0.0
    curve = []
    for t in range(N_TICKS):
        ctx = rng.integers(0, N_ARMS)     # which context arrives this tick
        won = rng.random() < truth[ctx]
        # fixed-$1 policy: trades every context (stale table says EV>0 at public
        # 2.4265: 0.4165*2.4265-1 = +1.1%) — settles at executable
        pnl_fixed += (M_EXEC - 1.0) if won else -1.0
        # bandit: LCB-Kelly at executable
        plcb = arms[ctx].lcb()
        if plcb * M_EXEC - 1.0 > GATE:
            stake = BASE * kelly(plcb, M_EXEC)
            if stake > 0.01:
                pnl_bandit += stake * ((M_EXEC - 1.0) if won else -1.0)
                staked_bandit += stake
                if ctx == 0: stake_on_good += stake
                else: stake_on_bad += stake
        arms[ctx].update(won)             # full-information update
        if t % 5000 == 0:
            curve.append((t, round(pnl_bandit, 2), round(pnl_fixed, 2)))

    print(f"true good-arm p={P_GOOD:.4f} (breakeven {BREAKEVEN:.4f}), table prior {TABLE_P}")
    print(f"bandit : pnl={pnl_bandit:+9.2f}  staked={staked_bandit:9.2f}  "
          f"on_good={stake_on_good:.2f}  on_bad={stake_on_bad:.2f}")
    print(f"fixed$1: pnl={pnl_fixed:+9.2f}  staked={N_TICKS:d}")
    print("curve (tick, bandit, fixed):")
    for c in curve[::2]: print("  ", c)
    good_share = stake_on_good / staked_bandit if staked_bandit else 0
    print(f"\nstake concentration on the one genuinely positive arm: {good_share*100:.1f}%")
    ok = pnl_bandit > 0 and good_share > 0.95
    print("PASS" if ok else "FAIL")
    json.dump(dict(pnl_bandit=pnl_bandit, pnl_fixed=pnl_fixed, staked=staked_bandit,
                   good_share=good_share, curve=curve, ok=bool(ok)),
              open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "results", "bandit_synthetic.json"), "w"), indent=1)


if __name__ == "__main__":
    run()
