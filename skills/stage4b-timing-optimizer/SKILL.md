---
name: stage4b-timing-optimizer
description: Use when optimizing asset-specific Stage 4B timing filters for Motis Quant Terminal after Stage 4A exists.
---

# Stage 4B Timing Optimizer

## Purpose
Find asset-specific UTC timing windows that improve realized Stage 4 replay by converting existing `LONG`/`SHORT` calls to `SKIP`. Do not change direction logic, TP/SL, pyramiding, sizing, leverage, confidence, or execution behavior.

## Required Inputs
- `promotion/stage4b_timing/timing_context.json`
- `promotion/stage1a_canonical_full_cycle_scores.json`
- `promotion/stage4_realized_expectancy.json`
- `promotion/stage4_trade_ledger.json`
- `promotion/stage4_candidates.json`
- Raw 5m candles for the session asset
- Full signal rows or enough local artifacts to reconstruct replay signal rows

## Rules
- Use packet/signal timestamps in UTC only.
- Build timing evidence from the full canonical decision set, not only the filled Stage 4 ledger.
- Prefer broad recurring windows: UTC hours, contiguous hour blocks, or UTC weekdays.
- Keep filters asset-specific. Never copy a timing window from another asset without testing this asset.
- Reject exact dates, exact timestamps, exact signal IDs, one-off clusters, or event hindsight.
- Preserve the existing strategy decision first, then apply timing as an abstention wrapper.
- The overlay may only turn a matching `LONG` or `SHORT` into `SKIP`.

## Required Workflow
1. Load `timing_context.json` and confirm the `source_stage4_run_id` matches the active top-level `promotion/stage4_realized_expectancy.json` run id unless the user explicitly names a different Stage 4A run.
2. Build UTC timing buckets from every canonical Stage 1 record, including records later skipped by Stage 4 because a position was already open.
3. Split bucket evidence by `sample_role`: use training data to propose candidate weak windows, and use walk-forward only to confirm or reject them.
4. For each UTC hour and simple contiguous hour block, measure:
   - total records removed and coverage retained
   - directional agreement kept vs removed
   - training agreement kept vs removed
   - walk-forward agreement kept vs removed
   - LONG/SHORT impact if a side-specific filter is being considered
5. Prefer the smallest broad window that removes a recurring training-supported weak area. Do not add a walk-forward-only hour just because it improves the final result.
6. Treat the `source_stage4_candidate_id` as the decision anchor. If integrated replay scores all candidates, report the source candidate metrics first and the replay-selected best candidate second.
7. Write one overlay candidate, then run the integrated Stage 4B timing replay. If the first overlay fails realized validation, narrow or side-scope it using training-supported evidence and rerun. Do not add walk-forward-only hours during retries.

## Search Defaults
- Test all single UTC hours.
- Test simple non-wrapping contiguous UTC hour blocks of length 2 through 6.
- Start with `applies_to: "all"`. Test `LONG` and `SHORT` side-specific overlays when all-side filters fail realized validation or side buckets show materially different behavior.
- Reject sparse bucket candidates unless they have enough observations to be meaningful for this session. As a default, prefer at least 40 training records for all-side windows, 20 training records for side-specific windows, and non-trivial walk-forward confirmation.

## Replay Input Reconstruction
Use the integrated Stage 4B replay path, not a filled-trade approximation. The replay needs session metadata, signal rows, and raw candles.

- Build session metadata from the session `manifest.json`: `session_id`, `artifact_root`, `asset`, strategy/signal ids, `train_start`, `train_end`, `walk_forward_start`, and `walk_forward_end`.
- Prefer full canonical signal rows or packet artifacts when present.
- If full packet rows are absent, reconstruct minimal signal rows only when the reference price can be validated from local artifacts. For 5m candle-close engines, parse the UTC timestamp from the canonical `signal_id`, set `payload.timestamp`, and set `payload.evidence.reference_price` / `trigger_candle_close` from the raw 5m candle close. Cross-check against any Stage 2 per-signal capture artifact before trusting the reconstruction.
- Load raw 5m candles through the walk-forward end plus the Stage 4 max hold buffer.
- Before trusting Stage 4B output from reconstructed rows, sanity-check that the source Stage 4A candidate can be recalculated to match persisted Stage 4A metrics.

## Decision Standard
Accept a timing overlay only when it has a coherent training-supported reason and does not damage walk-forward realized quality. Directional accuracy is evidence, not the objective. Reject or narrow a filter that improves agreement but lowers walk-forward return or materially lowers walk-forward profit factor versus the Stage 4A source candidate. Prefer overlays that improve both walk-forward return and walk-forward profit factor while keeping the skipped-by-timing count explainable.

The BTC/ETH/BNB pattern this skill is meant to reproduce is:
- find weak UTC windows from canonical decision buckets, not from filled trades only
- test broad hour blocks such as `12-14 UTC`, `00-02 UTC`, or `16-20 UTC`
- validate with a true sequential Stage 4B replay using the same Stage 4A setup
- avoid one-off additions that are only justified by the walk-forward outcome

## Output
Write `promotion/stage4b_timing/timing_overlay.json`:

```json
{
  "schema_version": "stage4b_timing_overlay.v1",
  "source_stage4_run_id": "stage4-...",
  "source_stage4_candidate_id": "candidate-id",
  "exclude_utc_hours": [16, 17, 18],
  "exclude_utc_weekdays": [],
  "applies_to": "all",
  "rationale": "Training-supported recurring weak UTC window with walk-forward confirmation."
}
```

`applies_to` must be `all`, `LONG`, or `SHORT`. Use `exclude_utc_weekdays` only when weekday/weekend behavior is clearly supported.

## Evaluation Standard
Compare Stage 4B against Stage 4A using ending equity, net PnL, win rate, profit factor, walk-forward return, walk-forward profit factor, executed trades, and skipped-by-timing count. A timing filter is weak if it improves directional accuracy but degrades realized walk-forward performance.

The final response should include the chosen UTC hours, `applies_to`, bucket evidence for training and walk-forward, Stage 4A vs Stage 4B source-candidate metrics, replay-selected best candidate if different, and the replay artifact paths.

## Common Mistakes
- Optimizing from filled trades only; this ignores signals skipped by open positions.
- Picking an hour because it is bad in walk-forward but not supported by training.
- Accepting an all-side filter after replay shows it damages walk-forward realized return/PF; narrow or side-scope only if training buckets support it.
- Letting replay choose a different best candidate without reporting the named source candidate separately.
- Running an approximate replay without validating reconstructed signal rows against Stage 2 capture or persisted Stage 4A metrics.
- Treating timing as a direction flip.
- Adding TP/SL or sizing edits to the overlay.
- Using local clock time instead of packet UTC time.
