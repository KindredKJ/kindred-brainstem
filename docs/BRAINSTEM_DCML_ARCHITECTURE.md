# BRAINSTEM-DCML architecture

## Identity and boundary

**BRAINSTEM is the model. DCML is BRAINSTEM's native cognitive-learning mechanism.** The FastAPI process is a serving runtime; it does not define BRAINSTEM's identity or intelligence. Attached providers are subordinate cognitive instruments. They receive BRAINSTEM-framed tasks and selected context, then return a specialist result and telemetry.

```text
CLI -> serving runtime -> BrainstemModel
                         |-- persistent cognitive state
                         |-- structured world model
                         |-- beliefs and contradictions
                         |-- memory retrieval
                         |-- strategy generation and simulation
                         |-- metacognitive evaluation
                         |-- governed DCML learning
                         `-- attached cognitive instruments
```

## One cognitive operation

`BrainstemModel.cognitive_cycle` performs one coherent operation: perceive; recall; revise the working view of beliefs; identify constraints through the strategy policy; generate strategies; create a prediction and counterfactual; estimate utility, uncertainty, and risk; decide; frame and invoke an instrument; reflect on the result; assign prediction error; propose governed learning; and persist the verified state revision.

An instrument failure records telemetry and an experience outcome but does not commit a new cognitive-state revision. No fallback instrument is selected silently.

## Persistent cognitive state

The versioned `CognitiveState` owns current context, goals, intentions, uncertainty, contradictions, working/episodic/semantic/procedural memory references, learned strategies, and capability history. Beliefs retain confidence and provenance. Contradictory values are both retained as `CONFLICTED`; neither silently overwrites the other.

The world model uses typed nodes and relationships with confidence, provenance, causal strength, and revision. Predictions, counterfactuals, observed outcomes, and prediction errors are separate records rather than unstructured chat messages.

## Capability status

* Native symbolic/stateful DCML foundation: `AVAILABLE`, covered by deterministic proof tests.
* Persistent cognitive state and migrations: `VERIFIED` by restart and migration tests.
* Foundation-model parameter training: `NOT_CONFIGURED`; no parameter training occurred.
* Learned strategy activation: governed and `AVAILABLE`; requires evaluation and explicit founder approval.
* Autonomous production learning: `NOT_IMPLEMENTED` and prohibited.
