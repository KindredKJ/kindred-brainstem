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
