# DCML pre-implementation repository audit

Audit date: 2026-07-29. This document records the verified state before the native model layer was introduced.

## Existing boundaries and abstractions

* `brainstem/runtime/` was a loopback FastAPI orchestration service with SQLite persistence. Its `RuntimeService.chat` method owned context assembly, adapter selection, evidence creation, and learning proposal creation. That incorrectly located cognitive-cycle logic in the serving runtime.
* `brainstem/adapters/models/` already provided a useful provider-independent `ModelAdapter` boundary and concrete Codex, HCarat, and OpenAI-compatible adapters. Health gating and the no-fallback rule were reusable.
* `brainstem/runtime/store.py` provided a useful canonical SQLite database, JSONL event export, session history, and transactional backup/restore, but it had no migrations or typed cognitive/world-model schema.
* `brainstem/engines/associative_memory_engine` was a JSONL keyword matcher. It was reusable only as legacy input, not as canonical cognitive memory.
* `brainstem/engines/backprop_engine` calculated fixed planning losses and explicitly performed no model training. It was a placeholder, not DCML or gradient backpropagation.
* `brainstem/engines/model_runtime` returned a deterministic formatted string. It was a placeholder, not a trainable model.
* `brainstem/engines/founder_approval_plane` and ledger modules were JSONL helpers. Their founder-gating doctrine was reusable, but they were not transactionally connected to learning promotion.
* Evidence, result, audit, approval, associative-memory, and backprop records existed across separate JSONL files. The newer runtime database was the appropriate migration target while preserving those files unchanged.

## Incorrect descriptions found

Earlier documentation and module descriptions called BRAINSTEM a “runtime” or “runtime service.” The corrected boundary is: **BRAINSTEM is the model; DCML is its native cognitive-learning mechanism; the runtime only serves and orchestrates the model.** Runtime health does not establish intelligence or trained weights.

## Verified training state

No H^ implementation or weights were found, no parameter-training pipeline had executed, no checkpoint represented trained parameters, and no pre/post-training evaluation existed. Therefore model-weight status was and remains `NOT_TRAINED`. This implementation adds a formal future training boundary and reference dataset export, not trained foundation-model weights.
