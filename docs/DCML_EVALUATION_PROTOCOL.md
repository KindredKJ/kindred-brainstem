# DCML evaluation protocol

## Cognitive-cycle evaluation

For every successful cycle BRAINSTEM stores the selected strategy, predicted outcome and probability, counterfactual intervention, observed outcome, prediction error, capability telemetry, evidence link, and state revision. Metacognitive evaluation records confidence-calibration error, missing information, and detected failure categories.

An externally observed outcome can be compared with a prior prediction. Non-zero prediction error creates a provenance-linked learning proposal. It does not activate the lesson.

## Learning evaluation

Before approval, an evaluator records a numeric score and evidence identifiers. Approval, promotion, and activation are separate operations. Evaluation must cover expected benefit, regression risk, authority impact, evidence sufficiency, and rollback feasibility. Conflicting evidence should transition the proposal to `CONFLICTED`, not overwrite it.

## Future parameter evaluation

Before any adapter or parameter training, an approved dataset must be versioned and split. A future `ParameterTrainer` must implement pre-training evaluation, checkpointed training, post-training evaluation, and rollback. Evaluation results and checkpoint hashes must be stored before any trained status may be claimed.

## Current evidence

Automated proof tests cover restart persistence, context ownership, clean-response/telemetry separation, prediction error, approval gates, behavioral activation, rejection, belief conflicts, learning rollback, checkpoint rollback, failure isolation, schema migration, and runtime/model separation. No real Codex test can pass in the current environment because the executable is absent; this remains an explicit environment blocker rather than a simulated success.
