# Kindred BRAINSTEM serving architecture

```text
kindred (Typer client)
  -> HTTP on 127.0.0.1:8280
     -> FastAPI serving runtime
        -> native BrainstemModel / DCML cognition
        -> transport and session orchestration
        -> SQLite canonical state
        -> JSONL append-only audit export
        -> provider-independent adapter registry
           -> H^ endpoint (NOT_CONFIGURED until probed)
           -> Codex CLI (NOT_CONFIGURED until probed)
           -> explicitly configured OpenAI-compatible provider
```

The native BRAINSTEM model, rather than the serving runtime or an adapter, creates the session, assembles conversation history, chooses the explicitly selected route, records events and evidence, and creates candidate learning proposals. Switching adapters changes only `sessions.model`; history remains owned by the session.

## State boundaries

Global state is stored in `~/.kindred/brainstem.db`. Repository state stores only the active session pointer under `<repo>/.kindred/`; the global database remains canonical so sessions survive directory and process restarts. Audit exports are written beside the global database.

## Operations

PowerShell startup:

```powershell
python -m pip install -e ".[dev]"
kindred runtime start
kindred runtime status
kindred shell
```

Configure an explicit OpenAI-compatible endpoint:

```powershell
$env:KINDRED_MODEL_BASE_URL = "http://127.0.0.1:11434/v1"
$env:KINDRED_MODEL_NAME = "the-exact-installed-model-name"
kindred runtime stop
kindred runtime start
kindred shell
```

Rollback:

```powershell
kindred runtime stop
git revert <this-commit>
```

Back up `~/.kindred/brainstem.db`, its `-wal`/`-shm` companions when present, and `~/.kindred/events.jsonl` while the runtime is stopped. Restore those files to the same location before restarting.

## Native organizational awareness — first executable slice

BRAINSTEM owns the durable workforce observation table in its canonical SQLite
database. Organizational awareness is part of the native `BrainstemModel`,
appears in `GET /world`, and its summary is included in the cognitive cycle's
recorded context. EMIT is a replaceable source of observations, not a second
cognitive orchestrator.

Native endpoints:
- `GET /awareness` and `GET /awareness/workers`: persisted observations
  with heartbeat freshness, source errors and counts.
- `POST /awareness/workers/observe`: authenticates with
  `BRAINSTEM_AWARENESS_KEY` in `X-Brainstem-Awareness-Key`; accepts a local
  or other authorized worker observation without EMIT.
- `POST /awareness/sync`: authenticated immediate pull from EMIT.
- Automatic 15-second polling while the BRAINSTEM runtime serves, **only**
  when `KINDRED_EMIT_CORE_URL` and `KINDRED_INTERNAL_SERVICE_KEY`
  are configured. The EMIT URL must be HTTPS, or loopback HTTP for local
  development.

For local integration, point `KINDRED_EMIT_CORE_URL` at the EMIT server's base
URL (typically `http://127.0.0.1:8000`), set
`KINDRED_INTERNAL_SERVICE_KEY` to the same secret configured in EMIT,
and set an independent `BRAINSTEM_AWARENESS_KEY` for native submissions.
Then start both services and inspect `GET /awareness/workers`.

The inventory contract is `kindred.workforce.inventory.v1`.
EMIT's registered agents and configured lanes are **not** counted as active
workers. An observation can become stale after 60 seconds; a reported heartbeat
is not independent verification of external task completion. On failure, prior
observations remain available with their freshness and the sync error.

This slice gives the native model persistent operational *observations*, not
sentience, autonomous organizational decision-making, or independently proven
worker results. Next steps are individual worker adapters, verified outcomes,
root-signed evidence and cognition-driven intervention.
