# DCML causal and counterfactual state

Migration 2 provides durable causal-hypothesis, intervention, confounder, alternative-cause, counterfactual-decision, and lineage stores. Migration 4 adds separately persisted interventions and counterfactual observations.

The executable evaluator records expected and observed effects, adjusts causal confidence, and classifies an intervention as `STRENGTHENED`, `WEAKENED`, or `REJECTED`. Confounders, alternative causes, and falsification evidence remain attached to the hypothesis. Correlation is never labeled verified causation.

Counterfactual decisions compare multiple strategies on success, cost, latency, risk, reversibility, evidence requirements, and uncertainty. After observation, positive regret is persisted and may create a governed learning proposal; it does not directly activate a policy.
