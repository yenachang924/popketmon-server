# POPKEMON UX Experiments

## Operating Rules

- Measurement comes first. No UI or behavior change ships without a hypothesis, metric, expected direction, and minimum sample.
- One deployment equals one hypothesis, unless bundled changes use non-overlapping metrics.
- Low traffic means before/after time-series comparison. If the minimum sample is not met, the result is `판정 보류`.
- Every result records confidence: `높음`, `중간`, or `낮음`.
- Do not change the score monotonicity invariant or the four existing public game API contracts.

## Deployments

| Tag | Date/Time | Type | Hypothesis | Expected Metric Direction | Notes |
| --- | --- | --- | --- | --- | --- |
| phase-1-funnel-instrumentation | 2026-08-09 KST | Instrumentation only | Baseline collection | No UX metric target | Added `/events`, `/analytics/funnel`, and dashboard funnel section. No intentional UX improvement. |

## Baseline Gate

Phase 1 baseline starts after `phase-1-funnel-instrumentation` reaches production.

Minimum baseline before the first UX hypothesis deployment:

- 3 to 5 calendar days, or
- 30 users, or
- 100 sessions,

whichever arrives first.

If the funnel dashboard has no non-zero values for visit, first pop, 10 pops, name set, and ranking view, the baseline gate is not passed.

## Approved Hypothesis Queue

Owner approved all Phase 2 hypotheses on 2026-08-09 KST. They must still ship one at a time in this order.

| Order | ID | Hypothesis | Design Rationale | Primary Metrics | Expected Direction | Minimum Sample | Size | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | H1 | Delay trainer name input until after value is experienced. | Asking for a name before the first pop creates pre-value friction. | `median_first_pop_ms`, `pop_10_to_name_set_rate`, `name_sets` | first pop time down, name-set conversion up | 30 visitors or 100 sessions | M | Implementation prepared, waiting for owner review and baseline |
| 2 | H4 | Reduce mobile tapping friction and keep the core game in one screen. | The game loop depends on fast repeated taps; small viewports should prioritize the arena and progress feedback. | `avg_session_pops`, `median_session_seconds`, `first_pop_to_10_rate` | pops/session up, early drop-off down | 50 mobile sessions, if device split is available; otherwise 100 sessions | S | Approved, queued |
| 3 | H3 | Add personal ranking context: nearby players and next-rank gap. | A top-10 list gives weak motivation to players outside the top group. | `refresh_clicks`, `visit_to_ranking_rate`, `return_visit_rate` | refresh and return rates up | 50 ranking views | M | Approved, queued |
| 4 | H2 | Strengthen reward feedback around charge and milestones. | The first 10 pops are the fun-confirmation window; feedback should make progress feel earned. | `first_pop_to_10_rate`, `avg_session_pops`, `median_session_seconds` | 10-pop conversion and session pops up | 50 first-pop users | M | Approved, queued |

## Decision Template

Use this for each hypothesis after its minimum sample is met.

| Field | Value |
| --- | --- |
| Hypothesis |  |
| Deployment tag/time |  |
| Before window |  |
| After window |  |
| Minimum sample met |  |
| Primary metric delta |  |
| Secondary metric delta |  |
| Decision | 개선 / 중립 / 악화 / 판정 보류 |
| Confidence | 높음 / 중간 / 낮음 |
| Notes |  |
