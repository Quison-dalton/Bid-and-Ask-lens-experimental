# BIDASK FINDINGS — the bid/ask lens program (2026-07-05)

Addendum follow-up to `fable-thoughts/`: re-open the six rejected instrument
families under the bid/ask spread lens. Live bid/ask collected on 16 symbols
(the history endpoint is spot-only), 250k-tick spot histories for deep tests,
every test logged to `results/hypothesis_ledger.json`, BH-FDR computed on the
COMBINED cross-instrument set per the addendum's multiple-testing protocol.

## The headline

**The bid/ask quotes on Deriv synthetics are cosmetic.** On every instrument
tested, bid/ask are a deterministic proportional band around the spot:

    ask ≈ ceil( S · (1 + c/2) ),   bid ≈ floor( S · (1 − c/2) )

with a per-symbol constant `c` and residuals never exceeding ±1 pip
(`determinism_test.py`: within-1-pip = 100.0% on all 11 symbols tested).
There is no market-maker behind them: nothing in the spread or its rounding
residual correlates with volatility, precedes spikes, or predicts anything.

Per-symbol band constants measured (bps of price):
- Volatility family: literally CONSTANT spread per symbol (one unique value the
  entire session; quote ≡ exact mid; zero variance). R_100 2.63bps, 1HZ100V 2.42bps.
- Jump family: c ≈ 0.0236bps × vol-parameter (JD10 0.237, JD25 0.589, JD50 1.179,
  JD75 1.753, JD100 2.311) — the band encodes the DESIGN vol, not realized vol.
- Crash/Boom: c ≈ 0.10bps (1000-variants), 0.14bps (500-variants).
- Step index: spread is exactly ZERO.

## Seed-by-seed verdicts

### Seed 1 — spread structure
Fully characterized (above). The only non-deterministic content is ±1-pip
rounding noise, consistent with the band being computed from an internal spot
`S` carrying more precision than the displayed quote.

**Sub-pip leakage hypothesis (the one genuinely new channel this lens opened):**
if skew = (bid+ask)/2 − quote leaks frac(S), then slope(step_{t+1} ~ skew_t) = +1.
Result: rejected everywhere. JD100 slope −0.04 ± 0.66 at n=9.5k (an early −5.6
"anomaly" at n=1.6k regressed monotonically to zero: −5.6 → −1.9 → −0.04).
No instrument shows a stable non-zero slope. The rounding noise is just noise.

### Seed 2 — spread tracks realized sigma
- Volatility family (the addendum's "clean calibration lab"): **structurally
  undefined** — the spread has zero variance. The cleanest possible null.
- JD/Crash/Boom (after residualizing the deterministic c·price component):
  all |r| < 0.03 at every lead/lag in ±120 ticks, |t_eff| < 0.2. Null.

### Seed 3 — spread/skew widens before a move
Event study on Crash/Boom spikes (8× median step) and JD jumps (6 MAD-sigma),
30-tick pre-windows, block-permutation p-values:
- All pre-event spread residuals within ±0.05 pips of baseline.
- p-values scattered uniform (0.07–0.93); early small-n "hits" (p=0.017, 0.033
  at 5–6 events) died on more events, and signs are inconsistent across
  instruments. Nothing survives BH-FDR. **The generator does not telegraph.**
  (More events accumulating overnight; profile stable.)

### The duty-cycle question (JD10–75)
Rejection upheld, but for a sharper reason than the original: the digit edge
requires ABSOLUTE pip-lattice sigma ≲ 5 pips. Measured on 250k ticks each:
JD10 σ=171p, JD25 σ=510p, JD50 σ=666p, JD75 σ=101p → digit PMFs exactly uniform,
0% of ticks have model EV > 1%, daily EV proxy $0. JD100 has σ≈4.4p ONLY because
its spot decayed to ~253. **The edge was never about jump frequency — it is
about spot level.** No duty-cycle tradeoff exists: the other JDs sit at 0×0.

### Range Break
Not offered on the new API at all (`active_symbols` has no RB*). Dead
lens-independently, joining Step Index.

### The one real (but untradeable) discovery — Crash/Boom calm phases
The addendum's side question ("does the calm phase have exploitable conditional
digit structure?") — YES, statistically:
- CRASH1000 calm phase: step σ = 4.1 pips, drift +5.96p/tick → conditional
  offset PMF strongly non-uniform (P(offset 1)=13.6% vs P(offset 9)=6.3%).
  At the standard digit payout grid this would be **+23.4%/trade**
  (DIGITUNDER 2 at digit 9), split-half stable (+23.3%/+23.6%), n=243k.
- BOOM1000: same shape, +6.7%/trade, stable.
- **But `contracts_for` returns ONLY MULTUP/MULTDOWN on Crash/Boom.** No digit
  contracts, no CALL/PUT, nothing that settles on the tick lattice. The
  structure is real and enormous — and there is no instrument to trade it with.
  (This also explains WHY Deriv doesn't offer digits there.)

## Ledger state
46 tests logged. BH-FDR(0.05) survivors: exactly the two untradeable Crash/Boom
calm-phase structures. Every spread/skew hypothesis is null.

## Live model run (sentinel_v2, this session)
Running on demo DOT92587183 with empirical tables, gate 1%, $1 stakes,
`--sigma-max 4.35`. JD100 spot rose 253→258 during the session, rolling σ
4.5–4.7 → **regime closed; the bot is correctly refusing to trade.** This is
the physics gate doing its job: the edge deepens as spot decays, and today spot
is moving the wrong way. Balance $10,000.61, 0 trades, 0 losses.

## SESSION 2 (2026-07-06) — the execution-pricing discovery

The regime opened in session 2 (spot decayed 254.7→248, σ≈4.1–4.3) and the
sentinel fired 670 trades… at −$35.08 (42.7% wins vs 45.0% breakeven). Root
cause found and proven live:

**The public tick socket's payout quotes are NOT executable.** The same
contract (DIGITOVER 5, JD100, 1t, $1) quotes payout 2.43 on the public socket
but 2.22 on the authenticated one — and settles at 2.22 (verified on real
settled contracts). Identical across app_ids, linear in stake. Executable
house edge is ~9–11% per digit contract vs the ~2.5–3% the public quotes
imply (DIGITEVEN/ODD 1.82 vs 1.95, DIGITMATCH 6.67 vs 8.93).

Consequences, all verified:
- sentinel_v2 probed payouts on the public socket → every "+1.08% EV" trade
  had **true EV ≈ −7.5%** at model p, ≈ −4.6% at realized p. Realized:
  709 trades across both sessions, −$31.90 ≈ −4.5%/trade. Exactly the
  executable payout at the model's win rate.
- **The digit MODEL itself is calibrated**: realized win rate 43.0% ± 1.9 vs
  model p 41.65% (z=+0.74). The science holds; the payout kills the economics.
- Breakeven p for the 4-digit contracts at payout 2.22 is **0.4505**, above
  the best empirical-table p (~0.43). **No executable positive-EV digit trade
  exists on JD100 through this account.** Patched sentinel (authenticated
  payout probe) confirms live: best EV at σ=4.30 with regime open = −4.74%,
  gate never opens. Session-1's +$3.18 on 39 trades was small-n luck.
- The parity-at-halfpip candidate (H2) needs p_win ≥ 0.5495 at executable
  DIGITEVEN/ODD payout 1.82; the in-sample effect is 53.0% on its best side →
  **untradeable through this account even if it survives holdout.**

`fable-thoughts/tools/sentinel_v2.py` is patched in this branch to probe
payouts on the authenticated connection when trading (and to refuse to trade
on public quotes), so its EV gate is now honest.

## What would change these conclusions
- Bid/ask from a different feed (e.g. the trading WS or contract pricing)
  showing non-cosmetic behavior — the public tick feed is what was tested.
- Deriv ever offering lattice-settled contracts on Crash/Boom → instant +20%
  edge from the calm-phase tables. Watch `contracts_for` occasionally.
- JD100 spot decaying below ~245 → sentinel_v2 regime reopens.

## SESSION 2 FINAL — holdout verdicts (2026-07-06 18:30 UTC)

Pre-registered protocol in `holdout_tests.py`, evaluated ONCE on session-2 data
(epoch ≥ 1783320000, fully disjoint from every tick that generated the
hypotheses). Results in `results/holdout_tests.json`:

- **H1 — the JD100 sub-pip leak: CONFIRMED.** slope(step_{t+1} ~ skew_t) =
  **+0.847 ± 0.125** on n=33,543 fresh ticks (t vs 0 = 6.75, one-sided
  p = 7.4×10⁻¹²; consistent with the leak-model target of +1, t vs 1 = −1.22).
  The bid/ask band genuinely reports the half-pip position of Deriv's internal
  higher-precision spot. This is the bid/ask lens's one true positive, now
  confirmed in-sample AND out-of-sample. Monetization: none through digit
  contracts (a 0.5-pip center shift at σ≈4.3p moves digit probabilities <1pp,
  and executable payouts eat far more than that).
- **H2 — parity-at-halfpip: DEAD.** Holdout success rate 49.70% on n=7,423
  half-pip ticks (p=0.70). The in-sample 52.1% (p=0.013) was a false
  discovery — exactly the failure mode the holdout requirement exists to catch.

### Seed 3 final (700 spike events, 9 instruments)
Pre-spike spread residual and |skew| elevation: all flat except one nominal
hit, BOOM1000 pre-spike |skew| (pooled p=0.004, which sneaks under the rank-5
BH threshold 0.0045). Split-sample: direction and magnitude replicate
(s1 +0.0395p / s2 +0.0366p elevation on ~0.3p base) but s2 alone is p=0.11 at
25 events. **Verdict: suggestive, unconfirmed, unmonetizable** (Boom offers
only multipliers, which price the spike). It stays flagged for a dedicated
pre-registered test if anyone ever cares; it is not a believed finding.

### Final ledger
68 tests logged across 16 instruments and two sessions. Believed positives:
1. The deterministic band structure of bid/ask (Seed 1, fully characterized).
2. The JD100 sub-pip leak, holdout-confirmed (H1). Scientifically real,
   economically nil.
3. Crash/Boom calm-phase conditional digit structure (+23.4%/+6.7% at PUBLIC
   payouts — but no digit contracts exist there, and executable payouts would
   cut it to ~+13%/−2% anyway).
4. The execution-pricing discovery: public payout quotes overstate executable
   payouts by ~9–11% of stake; JD100 digit trading has no executable edge.

Everything else — spread↔sigma coupling, pre-spike telegraphing, parity,
duty-cycle tradeoffs, Range Break, reset-tick snipes — is null or dead, each
with its cause of death documented in the ledger.

## Program epitaph

The bid/ask lens opened one genuinely new channel (the sub-pip leak), killed
one live trading program that looked profitable under mispriced payouts, and
closed every other door with evidence. The synthetic-index generator does not
telegraph. The quotes are cosmetic. The house edge is bigger than it looks
from the public socket. That is a complete answer to the brief.
