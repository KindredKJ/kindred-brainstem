# Kindred BRAINSTEM current-state assessment

Assessment date: 2026-07-29. Version: `0.1.0-alpha` (`0.1.0a0` package version).

## Verified repository state

The repository began this build as a Typer monolith. The earlier cognitive CLI wrote JSON files and printed unconditional `ONLINE`, `ACTIVE`, `READY`, and `VERIFIED` labels, but it did not run a model, a runtime service, H^, Codex, a world model, or an interactive conversation. Existing `model_runtime` code was a deterministic rule response, not an inference provider.

This vertical slice separates the CLI client from a loopback FastAPI runtime, establishes SQLite as canonical local state, exports audit events to JSONL, persists sessions and messages, and introduces provider-independent model adapters. Inference is available only when an adapter passes a real health probe.

## Capability matrix

| Capability | Status | Evidence / blocker |
|---|---|---|
| Local runtime API | AVAILABLE | Typed health, identity, sessions, chat, models, memory, world, evidence, missions, learning, events, and approvals routes. |
| SQLite session persistence | VERIFIED | Automated restart/reopen test reads the same session and conversation. |
| JSONL audit export | VERIFIED | Store tests verify emitted event records. |
| Interactive shell | AVAILABLE | Runtime-backed loop with recovery and slash commands. A real response requires a healthy configured adapter. |
| OpenAI-compatible adapter | AVAILABLE | Requires explicit endpoint/model configuration and a successful `/models` probe. No fallback occurs. |
| H^ / HCarat | NOT_CONFIGURED | No H^ implementation, weights, runtime, license, or configuration was found under `/workspace`, `/opt`, or `/root`. The generic endpoint is not represented as H^ unless explicitly configured and healthy. |
| Codex attachment | NOT_CONFIGURED | `codex` was not found on `PATH`; the adapter refuses invocation and records a failed model event. |
| Candidate learning | AVAILABLE | Successful responses create `PROPOSED` evaluation records only. Promotion is not implemented and remains blocked. |
| Evidence | AVAILABLE | Successful model calls create evidence records. |
| Memory promotion | NOT_IMPLEMENTED | Schema and read API exist; candidate conflict/policy workflow remains outstanding. |
| Versioned world model | NOT_IMPLEMENTED | API reports this status explicitly. |
| Missions | NOT_IMPLEMENTED | API reports this status explicitly. |
| Dashboard / remote runtime | NOT_IMPLEMENTED | No UI or remote deployment is included. |
| Streaming transport | NOT_IMPLEMENTED | Adapter contract supports iteration, but the current HTTP chat route returns a completed response. |

## Security findings

* Runtime binds only to `127.0.0.1`; remote exposure and authentication are not implemented.
* Provider keys are read from environment variables and are never persisted by BRAINSTEM.
* Model failures are surfaced and audited; no silent fallback is permitted.
* Production learning promotion has no route and is therefore blocked.
* SQLite is local and unencrypted. Filesystem access to `~/.kindred` must be restricted by the host account.
* The runtime currently lacks request authentication. Do not expose port 8280 beyond loopback.
* Codex command output may contain sensitive repository context. Review local evidence retention policy before enabling it.

## Founder decisions required

1. Supply and license the actual H^ runtime/weights or approve an explicitly named temporary provider.
2. Define retention, encryption, and backup policy for global and repository state.
3. Define the founder authentication mechanism before dashboard or remote work.
4. Approve memory conflict policy and the promotion state machine before canonical memory writes.
5. Decide whether model response bodies may be retained as evidence; this slice records metadata only.


## Native model correction

BRAINSTEM is now represented by `BrainstemModel`; DCML is fused into that model. The FastAPI runtime serves it and delegates cognition through the model interface. Structured cognitive state, beliefs, world nodes and causal relationships, experiences, predictions, counterfactuals, evaluations, strategies, skills, learning proposals, checkpoints, and telemetry use additive SQLite migration v1. No foundation-model parameter training occurred; trained-weight status is `NOT_TRAINED`.
