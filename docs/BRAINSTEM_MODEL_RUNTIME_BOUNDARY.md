# BRAINSTEM model/runtime boundary

## Model responsibilities

`BrainstemModel` owns identity, cognitive state, beliefs, structured world state, memory recall, strategies, simulation, predictions, counterfactuals, metacognition, learning transitions, checkpoints, rollback, and the framing/evaluation of specialist invocations.

## Runtime responsibilities

The runtime binds a local transport, probes storage and instruments, creates sessions, exposes typed APIs, delegates chat to `BrainstemModel.cognitive_cycle`, and returns serialized model results. It does not generate strategies, compute prediction error, approve learning, or mutate cognitive state directly.

## Instrument responsibilities

Adapters implement identity, capabilities, health, generation, streaming capability, cancellation, and usage. BRAINSTEM supplies the task frame, selected context, permissions, boundaries, and expected output. Clean assistant content is stored in conversation history. Commands, errors, token usage, and execution events are stored in telemetry. Codex NDJSON is parsed; raw event streams are not used as the assistant response.

## State and training distinctions

* **Memory learning** changes governed database records.
* **Policy learning** changes approved routing or decision records.
* **Prompt/strategy learning** activates evaluated procedures.
* **Adapter tuning** would create a separately identified adapter checkpoint.
* **Model-weight training** changes parameters and requires an approved dataset, evaluation split, pre/post evaluation, checkpoint identity, and rollback.

Only the first three have local reference mechanisms. Adapter tuning and weight training are formal interfaces only. Memory changes are never described as weight training.
