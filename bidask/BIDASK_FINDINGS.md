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

## What would change these conclusions
- Bid/ask from a different feed (e.g. the trading WS or contract pricing)
  showing non-cosmetic behavior — the public tick feed is what was tested.
- Deriv ever offering lattice-settled contracts on Crash/Boom → instant +20%
  edge from the calm-phase tables. Watch `contracts_for` occasionally.
- JD100 spot decaying below ~245 → sentinel_v2 regime reopens.
