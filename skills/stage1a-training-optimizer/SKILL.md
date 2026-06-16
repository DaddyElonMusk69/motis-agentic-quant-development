---
name: stage1a-training-optimizer
description: Training-only Stage 1A directional strategy optimization for agentic quant research. Use when Codex is asked to build or update a deterministic Stage 1A strategy script from a training failure audit, builder_training_sample.json, signal_sample.json, and packet evidence while avoiding validation, walk-forward, locked OOS, live execution, Stage 1B entry gates, or overfit feature-tree patches.
---

# Stage 1A Training Optimizer

## Purpose

Optimize a Stage 1A direction-only strategy script against the current training bundle, then stop. The user will run Score, validation, walk-forward, or locked OOS outside this skill.

Stage 1A asks one question: for scoreable signals, should `decide(...)` return `LONG` or `SHORT`? It does not decide whether the trade is worth entering.

The existing session `strategy.py` is a contract and context reference, not directional truth. Use it to understand the evaluator-facing decision shape, available packet fields, local helper style, and what failed. The optimizer may replace the directional premise or rewrite `decide(...)` substantially when the training evidence supports a simpler, stronger Stage 1A classifier. "Small" means simple, deterministic, explainable, and auditable; it does not mean the smallest diff from the previous directional bias.

## Hard Boundaries

- Read only the artifacts named in the user's training-iteration request.
- Use training labels only from `builder_training_sample.json`.
- Do not read validation, walk-forward, locked OOS, future candles, score files from later gates, or live state.
- Do not tune to exact timestamps, signal ids, or date clusters.
- Do not add Stage 1B entry gates, opportunity filters, expected-travel filters, trade management, order routing, exchange calls, randomness, or network access.
- Do not claim promotion readiness. Report only training-sample behavior and tell the user to rerun Score.
- Do not edit read-only snapshots, sample files, signal packets, audit files, or evaluator handoff files.
- Do not treat the seed strategy's directional bias as privileged. Preserve the decision contract, not necessarily the old rule logic.

## Required Inputs

Before editing, read:

- `failure_audit.json`
- `failure_audit.md`
- `builder_training_sample.json`
- `signal_sample.json`
- the mutable session `strategy_module/strategy.py`
- the iteration `source_artifacts/strategy_module_snapshot` as read-only evidence of what failed

If any required training artifact is missing, stop and report the blocker.

## Baseline Replay

Before proposing a replacement or rewrite, replay the current strategy on the training sample and report or record:

- scoreable count and LONG/SHORT label balance
- match, mismatch, and neutral counts
- directional agreement (match / called, where called = signals with a non-FLAT direction)
- called coverage = called / scoreable
- skip rate = neutral / scoreable
- failure counts by `reason_code`, truth direction, and decision direction
- LONG calls, SHORT calls, LONG agreement, and SHORT agreement when enough samples exist
- current MATCH cases and whether candidate changes regress them
- whether failures are mostly neutrality, wrong-way direction, or both
- whether full coverage or zero skips conflicts with a nontrivial natural null-GT rate

This replay is the comparator and contract reference. Do not edit before understanding it, but do not preserve its directional premise by default. If the old strategy is a weak seed, explore replacement premises directly.

## Neutral Rate Alignment

A strategy can inflate directional agreement by SKIP'ing signals with valid ground truth — converting potential mismatches into neutrals. It can also pass a rate check while skipping the wrong individual cases. To prevent this, every baseline replay and training verification must include both neutral-rate alignment and skip-accuracy checks.

### Methodology

Compute two rates from the training sample:

- **natural_null_gt_rate** = count of signals where `natural_direction` is `None` / total scoreable signals
- **strategy_neutral_rate** = count of signals where `decide(...)` returned `FLAT` / total scoreable signals

Also compute the neutral confusion counts:

- **true_neutral_skips** = count of signals where `natural_direction` is `None` and `decide(...)` returned `FLAT`
- **false_neutral_skips** = count of signals where `natural_direction` is `LONG` or `SHORT` and `decide(...)` returned `FLAT`
- **missed_neutral_entries** = count of signals where `natural_direction` is `None` and `decide(...)` returned `LONG` or `SHORT`
- **skip_accuracy** = true_neutral_skips / all strategy neutral decisions, when the strategy skips at least one signal
- **neutral_capture_rate** = true_neutral_skips / natural null-GT count, when the sample has natural null-GT signals

The natural null-GT rate represents the fraction of signals in the pool that genuinely lack directional resolution (did not cross the significance threshold within the observation window). For these signals, SKIP is the correct answer. A strategy should neither skip signals with valid ground truth (avoidance) nor enter signals with null ground truth (gambling).

### Deviation Rules

Report the deviation = `strategy_neutral_rate - natural_null_gt_rate`.

| Deviation | Interpretation | Flag |
|---|---|---|
| Within ±3pp | Aligned | None |
| Beyond ±3pp | Misaligned | Block — the strategy is either skipping signals it should be deciding, or entering signals with no directional resolution; agreement scores are unreliable |

### Skip Accuracy Rules

The neutral-rate check is necessary but not sufficient. A strategy can have the correct total number of skips while skipping directional ground-truth signals and entering neutral ground-truth signals.

Treat skip accuracy as the neutral equivalent of directional agreement:

- Report skip_accuracy and neutral_capture_rate alongside directional agreement.
- Treat false_neutral_skips and missed_neutral_entries as serious evidence of avoidance or gambling, especially when either count rises materially from baseline.
- Do not use false_neutral_skips or missed_neutral_entries as standalone hard gates; use them to explain whether skip behavior is healthy.
- Block an update only when skip_accuracy materially worsens from baseline, even if total skip rate remains within ±3pp.
- When natural null-GT count is tiny, report counts first and avoid overinterpreting percentage swings from one or two cases.

If the old strategy never skips, the neutral-rate and skip-accuracy checks still apply to candidate replacements. A candidate may intentionally introduce `FLAT` only when packet evidence supports true neutral resolution failure; it must not use `FLAT` as an avoidance bucket for hard directional cases.

### Zero-Skip / Full-Coverage Check

If `strategy_neutral_rate` is 0 while `natural_null_gt_rate` is nontrivial, treat this as an active coverage defect to investigate, not as a harmless full-coverage result. A 100% called strategy may be gambling on natural-null cases.

Before accepting a zero-skip strategy or concluding no skip rule is possible:

- compare natural null-GT cases against directional ground-truth cases using broad packet evidence
- look for stable regime differences that justify `FLAT`, such as higher-timeframe return, range position, momentum, volatility, volume, or event-context fields already present in packets
- test any candidate neutral resolver with neutral_capture_rate, skip_accuracy, false_neutral_skips, monthly coverage, and directional agreement impact
- reject `FLAT` rules that mostly skip valid directional labels or only work through narrow timestamp-like feature clusters
- explicitly report why no stable neutral signature was found when keeping full coverage

Do not force skips just to match the natural null-GT rate. The obligation is to investigate and justify coverage, not to manufacture neutral decisions.

### Regime Difference Heuristic

When skip_accuracy is weak, inspect skipped cases by broad regime features before treating the issue as a pure coverage problem. Compare true_neutral_skips, false_neutral_skips, and missed_neutral_entries using packet evidence such as:

- 1d and 2h base-candle return_pct
- 1d and 2h close_location_pct or range position
- 1d and 2h momentum or range-position features already present in the packet
- 5m volatility or Bollinger position only as context for why the original strategy skipped

If false_neutral_skips cluster in clear bullish or bearish higher-timeframe regimes while true_neutral_skips do not, prefer a broad regime-aware FLAT resolver over ad hoc coverage expansion. Keep the resolver directional, simple, and explainable; it should decide LONG/SHORT from general market context, not from timestamps, signal ids, or narrow feature trees.

When broadening an existing FLAT resolver, preserve any clearly stronger old rule path first unless replay proves the old path was wrong. Do not make a newly referenced field mandatory for an older valid path unless replay justifies it; missing-field changes can silently regress valid decisions.

### Monthly Coverage

Include strategy_neutral_rate per month alongside the monthly stability audit. Treat month-level drift as diagnostic context only, not as an additional hard gate.

## Monthly Stability Audit

Before handing back any edited strategy, evaluate training performance by calendar month. Use only timestamps and labels from the training sample.

Report or record:

- scoreable signal count per month
- monthly match, mismatch, and neutral counts
- monthly strategy_neutral_rate and deviation from natural_null_gt_rate
- monthly directional agreement
- monthly LONG agreement and SHORT agreement when enough samples exist
- worst-month agreement
- whether the improvement is concentrated in only one or two months
- whether any month regresses sharply from the baseline
- whether any side collapses, such as LONG working while SHORT fails

Use monthly stability as a training-only robustness check, not as a source for timestamp rules or hard rejection criteria.

When monthly stability is poor, prefer simplifying or rejecting the candidate update over maximizing aggregate training agreement. A lower aggregate score with smoother monthly behavior is preferable to a brittle high aggregate score.

## Direction And Coverage Diagnostics

Stage 1A rewrites must not buy higher aggregate agreement by becoming one-sided or skipping hard cases. Treat the following as diagnostics and recommendations, not independent gates.

### LONG/SHORT Imbalance

For baseline and updated replay, report:

- truth LONG count and truth SHORT count
- strategy LONG call count and strategy SHORT call count
- LONG agreement and SHORT agreement when each side has enough samples
- call imbalance = abs(LONG calls - SHORT calls) / called

Treat large side imbalance as a warning sign, not a standalone block:

- aggregate agreement improves but one side materially collapses from the current comparator
- one side has enough training samples but falls near random or below the current comparator by a meaningful margin
- call imbalance increases sharply without an explicit, broad directional rationale from packet evidence
- the rewrite effectively converts a two-sided signal into one-sided behavior without evidence

Do not force artificial symmetry when the training labels are genuinely imbalanced. The requirement is side stability relative to the sample, not equal LONG and SHORT counts.

### Skip Rate And Coverage Drop

For baseline and updated replay, report:

- scoreable count
- called count
- neutral count
- called coverage = called / scoreable
- skip rate = neutral / scoreable
- true_neutral_skips, false_neutral_skips, and missed_neutral_entries
- skip_accuracy and neutral_capture_rate
- coverage change versus baseline

Use coverage drop as a warning sign when agreement gains come from avoidance rather than better directionality. The hard stops remain the neutral-rate alignment and skip-accuracy rules above.

## Feature Audit Discipline

Feature audit is part of this skill as a diagnostic reference, not a separate optimization skill. Use it to explain failures and test whether packet evidence is stable enough to consider. Do not ask the user or another agent to consult the broader quant-development skill for feature-audit rules.

Run or implement a feature audit only as diagnostics. Useful packet evidence includes multi-timeframe returns, range positions, candle direction, active timeframes, feature blocks already embedded in packets, and existing strategy diagnostics.

When the full workspace artifacts are available and the paths are known, prefer the existing helper:

```bash
python3 /Users/haokaiqin/.codex/skills/agentic-quant-trading-development/scripts/analysis/signal_feature_audit.py \
  --signal-dir <stage0_scoreable_subset_packets_or_signal_packet_dir> \
  --ground-truth-dir <stage0_ground_truth_dir> \
  --stage1-score <current_stage1_score_json_if_available> \
  --out-csv <iteration_root>/audits/signal_feature_audit.csv \
  --out-json <iteration_root>/audits/signal_feature_audit.json
```

If those paths are not available, do a lightweight in-memory audit from `builder_training_sample.json`, `signal_sample.json`, and embedded packet evidence. Do not block a patch only because the helper cannot be run.

Feature audit may be used to:

- find broad differences between failed and protected training cases
- identify recurring failure patterns
- rank candidate packet evidence
- test whether a simple rule might help
- check whether a candidate feature behaves consistently by month and side
- compare changed-decision distributions by truth direction, old/new decision, reason_code, and month before accepting a candidate

Feature audit must not be used to:

- copy a fitted classifier into `strategy.py`
- maximize training accuracy at any cost
- hard-code deep decision trees
- add many narrow threshold branches
- justify a rule only because it improves the current replay
- justify a rule whose effect changes sign across months or sides

Treat feature thresholds as clues. Convert only durable, simple, explainable market patterns into strategy rules. Reject feature-derived rules when the apparent edge exists only in one dense month, only on LONG or SHORT, only in one narrow packet cluster, or only after large coverage reduction.

Do not require regime stability or create new regime labels.

## Strategy Construction Guidance

The optimizer may choose any deterministic Stage 1A direction logic that fits the decision contract and uses only available packet evidence. Acceptable shapes include:

- a full replacement premise, such as continuation instead of reversal
- event-type-specific rules
- broad regime-aware direction rules from existing timeframe, momentum, range-position, volatility, volume, or packet feature context
- a simple ordered rule set with a deterministic fallback

Do not start from "how can I minimally patch the old bias?" Start from "what simple Stage 1A classifier best explains the training evidence without leaking or overfitting?"

The old strategy remains useful for:

- required return-object fields and local helper style
- understanding available packet paths
- baseline comparison
- identifying regressions introduced by a candidate
- preserving behavior only when evidence says the old behavior is genuinely strong

Protected/current MATCH cases are diagnostics, not immutable constraints. A candidate can regress some old matches when it fixes more failures and improves stability. Reject regressions when they indicate the candidate is narrow, one-sided, timestamp-like, or contradicts a broad packet-evidence pattern.

## Rule Complexity Guidance

Keep each strategy simple. This is guidance for reviewability and generalization, not a standalone gate. Simplicity is measured by explainability and number of broad conditions, not by textual diff size from the old script.

- Prefer 1-5 broad directional rules or one compact scoring/voting rule.
- Use no more than 2-3 numeric thresholds per rule.
- Round numeric thresholds to broad zones unless exact domain constants already exist.
- Avoid nested logic deeper than two levels.
- Do not add special-case exceptions for protected cases by timestamp or id.
- Do not preserve old matches with rules that are narrower than the failure pattern itself.

A rule is acceptable only if it can be explained without saying "the tree picked this split."

## Rule Justification

For each candidate rule, be able to state:

- which training failure pattern it targets
- which packet evidence supports it
- why the evidence should be a general directional read
- which current-match training pattern it could regress
- why it remains Stage 1A direction-only

Reject candidate rules that do not have a clear directional interpretation.

## Editing Strategy.py

Patch only the mutable session strategy file named by the user. You may rewrite `decide(...)` and add or remove helpers as needed, provided the evaluator-facing contract is preserved.

The edited `decide(...)` must:

- return a deterministic StrategyDecision-compatible object or dict
- choose `LONG` or `SHORT` for scoreable signals when sufficient packet context exists
- include `confidence`
- include a stable `reason_code`
- include diagnostics explaining the packet evidence used
- preserve the existing decision contract fields used by the evaluator

Use existing local patterns in the strategy file. Add helper functions only when they reduce repeated logic or make diagnostics clearer.

## Training Verification

After editing, run:

- Python syntax verification, such as `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile <strategy.py>`
- a replay of the training sample
- a current-match regression check
- the neutral-rate alignment and skip-accuracy checks
- the zero-skip/full-coverage investigation when natural null-GT cases exist
- the monthly stability audit
- the LONG/SHORT imbalance audit
- the skip-rate, skip-accuracy, and coverage-drop audit
- a diff against the read-only strategy snapshot or a scoped diff of the edited strategy file

Report:

- baseline match/mismatch/neutral counts
- updated match/mismatch/neutral counts
- natural_null_gt_rate, strategy_neutral_rate, and deviation
- true_neutral_skips, false_neutral_skips, missed_neutral_entries, skip_accuracy, and neutral_capture_rate
- coverage/skip investigation result, especially when the updated strategy keeps 0 skips
- current-match cases preserved or regressed
- worst-month and monthly-stability result
- LONG/SHORT imbalance result
- skip-rate, skip-accuracy, and coverage-drop result
- changed rule summary
- targeted training failure patterns
- any verification command that could not be run

Do not treat the training replay as promotion evidence.

## Walk-Forward And OOS Handling

If the user provides validation, walk-forward, or locked OOS failure evidence and asks for a patch, do not edit from that evidence unless they also provide a fresh training bundle explicitly designated for optimization.

For failed validation, walk-forward, or locked OOS requests:

- write a postmortem only when instructed
- identify general failure hypotheses
- recommend a fresh training cycle if needed
- do not create same-cycle revision rules from gate labels

The user owns running Score and walk-forward after the training patch.

## Final Response Shape

Keep the final response concise:

- file edited
- deterministic rules changed
- training replay result (including natural_null_gt_rate, strategy_neutral_rate, deviation, skip_accuracy, and neutral_capture_rate)
- coverage/skip investigation result, especially if no skips are used
- current-match regression result
- monthly stability result
- LONG/SHORT imbalance result
- skip-rate, skip-accuracy, and coverage-drop result
- explicit note that validation/walk-forward/OOS was not used
- next action: user should rerun Score on the training iteration
