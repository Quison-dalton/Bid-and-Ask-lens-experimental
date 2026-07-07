# PHASE 2 — THE DYNAMIC MANDATE: FINDINGS
### Session 2026-07-07, branch `phase2-dynamic` (extends BIDASK_FINDINGS.md and the Phase 1/1.5 ledger)

## SECTION 5 ANSWER FIRST (the one question this session must answer)

**Given the current, freshly verified, executable payout surface: does any
(sigma_bin, contract, sizing_policy) combination clear its true breakeven with
a holdout-confirmed margin — and does layering bandit sizing + ML residual
correction widen that margin?**

**NO — and the decomposition is now exact.**

| Layer | Out-of-sample result | Verdict |
|---|---|---|
| Fresh payout discovery | 0/40 JD100 digit contracts clear breakeven at best model p; best case DIGITOVER:3 **−2.97%**. Surface byte-identical to session 2 → static haircut, not drift | closed the gap by **0** |
| Bandit sizing (Axis A) | Cannot create EV where none exists; correctly stakes **zero** on every real arm. Its value is *loss avoidance*: −$605 (Phase-1 policy) → **$0** | closes 100% of the *bleed*, 0% of the *gap* |
| ML residual (Axis C) | Log-loss worse on 5/5 walk-forward folds; negative incremental EV on both surfaces | closed the gap by **less than 0** |

The combined system (honest pricing + bandit + no-ML) beats the parametric
fixed-Kelly Phase-1 baseline by **+$605 out of sample** — entirely by refusing
to trade. There is nothing to harden and run live for profit; there is a
sizing architecture to keep for whenever a real edge is next found.

---

## Hours 0–2 — Executable payout surface, re-verified

All 40 JD100 digit contracts probed public + authenticated ($1, 1t), fresh:

- Authenticated haircut vs public quote: ~5% (near-even contracts) to ~25%
  (DIGITMATCH 8.93 → 6.67). DIGITOVER5/UNDER4: 2.43 → 2.22 (breakeven 0.4505).
- **Identical to session-2 values** on every overlapping contract → the
  executable surface did not drift in ~1 day. The toll booth's price is fixed.
- Best-case model p (max over all sigma bins × current digits, empirical
  tables): every contract negative. Full table in `results/payout_surface.json`.

## Axis A — Contextual bandit sizing (replacing fixed-fraction Kelly)

`bandit_sizing.py`: arms = (sigma_bin, digit, contract); Beta posterior per arm
seeded at table p with pseudo-n=200; **full-information updates** (digit
outcomes are public — every tick updates candidate arms whether traded or not);
stake = 25 × Kelly evaluated at the posterior 20% quantile (LCB), EV gate 1%,
always priced at the executable surface. Walk-forward replay, 74,833 ticks:

| Policy | Trades | Staked | PnL | PnL/$ |
|---|---|---|---|---|
| P0 Phase-1 sentinel (fixed $1, public-priced gate) | 6,333 | $6,333 | **−$605.44** | −9.56% |
| P1 half-Kelly at public payouts | 6,333 | $818 | −$72.30 | −8.84% |
| P2 honest static (fixed $1, exec-priced gate) | 0 | 0 | 0 | — |
| P3 bandit at executable payouts | 0 | 0 | 0 | — |
| P4 bandit fed the WRONG (public) payout belief | 8 | $5.19 | −$2.52 | — |

P4 is the operational point: even with a wrong payout table, posterior
uncertainty alone rescued 99.6% of the Phase-1 loss. **The bandit's posterior
is the live calibrator** — the stale-table problem is solved structurally.

**Synthetic edge-injection validation** (`bandit_synthetic.py`): one arm given
true p = breakeven + 2%, prior deliberately pessimistic (stale table p). The
bandit discovers it, concentrates **100%** of stake on it, +$146 while fixed-$1
loses −$5,435 on the same stream. The machinery scales up into real edges and
down to zero on fake ones. PASS.

## Axis B — Adversarial/responsive pricing experiment

`adversarial_pricing.py`, within-account block design (no second account
available): baseline authenticated probe → alternating 25-trade blocks of
DIGITDIFF:0 ("winning streak" arm, realized **89%** win rate) and DIGITMATCH:0
("losing streak" arm, realized **8%** win rate) → fresh authenticated probe of
6 contracts after every block, 8 cycles, 12-min gaps. 400 settled trades,
−$106.38 net, 17 probes.

**Result: payout variance across all 17 probes is exactly zero on every
contract** (2.22 / 2.22 / 1.82 / 1.82 / 6.67 / 1.05, unchanged to the cent).
No repricing after win streaks, loss streaks, or cumulative drawdown.

**Verdict: at this scale the house is a static distribution, not a reactive
opponent.** The 2.22-vs-2.43 gap is fixed account/tier pricing, not adaptive
risk management. Scope caveats (honest): single demo account, $1 stakes, 400
trades, ~3.5h window. Real-money accounts, larger stakes, or longer horizons
remain untested — but within everything testable here, the Stackelberg framing
is falsified; the stationary-market model stands.

## Axis C — ML residual layer

`ml_residual.py`: HistGradientBoosting 10-class model on offset, features =
current/last digits, fast+slow sigma, **skew** (the holdout-confirmed sub-pip
leak), spread, inter-arrival, UTC hour, ticks-since-jump, step — plus the
baseline table log-PMF as features (residual framing). Walk-forward only,
expanding window, 1800-tick purge/embargo, 5 folds, 74,775 rows.

- Log-loss: baseline 2.30204–2.30236 vs blended 2.30256–2.30864 —
  **worse on 5/5 folds** (sign-test p=0.06 that this is chance; direction is harm).
- Incremental EV: negative on both surfaces. At the executable surface the
  ML corrections manufacture 231 trades losing $69.20 where the honest
  baseline takes zero.
- Note the baseline itself sits barely below uniform entropy (ln10 = 2.30259)
  because most of the corpus is above the sigma gate where digits ARE uniform
  — the table's edge lives only in the thin low-sigma slice, exactly as
  established in Phase 1.

**REJECTED.** No higher-order structure (multi-digit memory, skew interaction,
time-of-day) exists in this corpus beyond the parametric core. The mandate's
own warning applied: an ML pattern with no mechanism is a spurious fit — here
walk-forward validation killed it before it could pretend otherwise.

## Ledger

72 tests total across all sessions. Phase 2 contributed 4 entries: three
structural rejections/nulls (payout surface, Axis B, Axis A-as-EV-source) and
one negative validation (Axis C). BH-FDR survivors unchanged from Phase 1
close-out: the calm-phase Crash/Boom structures (untradeable — no digit
contracts) and the JD100 sub-pip leak (real, holdout-confirmed, economically
nil). **No new survivor. No false discovery admitted.**

## What this session actually built (keep)

1. `payout_surface.py` — fresh executable-surface verification as a
   first-class, rerunnable step. Run it before ANY future trading idea.
2. The LCB-Kelly bandit sizing layer — validated in both directions. This is
   the correct permanent replacement for fixed-fraction Kelly the moment any
   instrument/contract shows a real executable edge.
3. The adversarial-pricing experiment harness — rerunnable on any account.
4. The walk-forward/purge ML validation harness — the template for any future
   learned layer.

## What would change these conclusions
- An account tier / broker route whose executable payouts approach the public
  quotes (the entire gap is 2.22 vs 2.43; the model's p≈0.43 clears 2.43's
  breakeven of 0.412 comfortably — **the physics still pays at the public
  price**; only this account's price kills it).
- Deriv offering lattice-settled contracts on Crash/Boom (+23% calm-phase
  structure is sitting there, confirmed and idle).
- JD100 spot decaying far enough that sigma drops materially below 4.0 — the
  tables' concentration (and p) rises as sigma falls.
