# bidask — the bid/ask lens program (2026-07-05 session)

Re-opens the instruments rejected by the spot-digit/sigma lens, under the bid/ask
spread lens, per the addendum to FABLE_OPEN_EXPLORATION_BRIEF.

- `collector.py`  — live multi-symbol tick collector (epoch, quote, bid, ask). The
  history endpoint returns spot only; bid/ask exist ONLY on the live stream.
- `seed1_structure.py` — what IS the spread? quantization, deterministic-in-price test, skew.
- `seed2_spread_sigma.py` — spread vs realized sigma, lead/lag. V100 = clean lab.
- `seed3_event_study.py` — does spread/skew widen before Crash/Boom spikes & JD jumps?
- `jd_duty_cycle.py` — JD10..JD100 duty-cycle EV tradeoff on 250k-tick histories.
- `ledger.py` — ONE hypothesis ledger across all instruments; BH-FDR on the combined set.

Notes fixed this session:
- Range Break (RB100/RB200) is NOT offered on the new API (`active_symbols` has no RB*):
  the addendum's item 3 is dead lens-independently, like Step Index for digits.
- Demo balance reset: POST /trading/v1/options/accounts/{id}/reset-demo-balance.
