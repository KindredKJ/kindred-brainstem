# Native BRAINSTEM DCML — Tool Choice and Observed Execution Feedback

This implementation reuses the existing canonical BRAINSTEM `BrainstemModel`, `RuntimeService`, SQLite `StateStore`, and `AdvancedDCML.counterfactual_decide` and `observe_counterfactual` mechanisms. It adds **no second model, no attached inference engine and no external language provider**.

## Native model-owned decision

`POST /dcml/native-tool-select` accepts the existing `brainstem-native` session ID, the wing's current objective, an array of **actual tools discovered from the live Autonomy gateway**, and the mission context. Each candidate has an exact name, factual description and risk class `read`. BRAINSTEM computes objective/capability overlap, bounds expected-success/risk/cost estimates, considers previously observed tool outcomes stored in its own DCML decisions, compares counterfactual alternatives through the existing advanced DCML decision method, and persists the chosen tool and scored alternatives under a decision ID and native evidence ID.

This is meaningful **structured, deterministic DCML policy inference**. It is not a neural language generation claim: lexical relevance and empirical observed execution are explicitly part of the initial scoring method. There is no wing-to-tool mapping inside the model; changing the objective, available tool descriptions, or observed history can change the chosen tool. Both the counterfactual decision and the state revision survive process restart.

## Recorded observation and adaptation

After Kindred Autonomy actually executes a read-only tool, the Continuum client verifies the gateway audit chain, the tool's successful execution, and the Continuum receipt's local event-chain integrity. Only then does it call `POST /dcml/native-tool-outcome` with the exact native session, selected tool, decision ID, a measured success boolean, SHA-256 of the provider's observed response, SHA-256 of the Continuum receipt, and SHA-256 of the Autonomy audit head.

The existing BRAINSTEM DCML stores the observation, marks the decision evaluated, persists native evidence and state revision, and uses the observed result to adjust subsequent utility scoring. Repeating an identical observation returns `already_recorded`; changing an observation for the same decision is rejected.

**Evidence limits:** these are observed authenticated provider-read results supplied by a verified local client, not independent third-party customer claims. A GitHub API response does not prove a customer purchase, business growth, prediction validity, model-weight training, or natural-language fluency. No unobserved counterfactual alternative is credited with an outcome. The APIs are localhost-local and do not add remote authentication.

## Real phone execution

See the companion [Continuum Termux v0.8 runner](https://github.com/KindredKJ/kindred-labs-superstructure/blob/feat/continuum-native-decision-execute-learn-20261120/labs/continuum/NATIVE_DECISION_FEEDBACK_TERMUX_V08.md). The runner starts actual BRAINSTEM and Kindred Autonomy on separate ephemeral localhost ports, uses copies of the original successful five-wing SQLite databases, and requires five BRAINSTEM-selected tool executions and five observed-feedback records. It separately proves at least one later expected-success score increases after an observed successful read.

## Targeted BRAINSTEM test

```bash
python -m pytest -q tests/test_native_tool_choice_feedback.py
```

The targeted suite verifies objective-dependent selection among four real read capability descriptions, candidate-risk restrictions, observed-failure changing a subsequent choice, feedback idempotency, session identity, persistence across restart, and no attached model use. The separate real Termux execution is required for actual provider evidence.
