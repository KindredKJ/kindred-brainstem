# BRAINSTEM Native DCML — Continuum Five-Wing Execution

**BRAINSTEM itself remains the cognitive model.** The new `BrainstemModel.native_cycle` calls native recall, strategy-policy selection, decision, prediction and counterfactual computation, durable experience/evidence storage, and an update to the same persistent `KINDRED-BRAINSTEM` cognitive state.

It does **not** route to an attached model, call a paid API, start a new serving engine, synthesize arbitrary English responses, fabricate customer outcomes, or train foundation-model weights.

## Native execution

Start the existing loopback BRAINSTEM service:

```powershell
kindred runtime start
kindred runtime status
```

To create an isolated wing session, call the existing runtime on localhost:

```powershell
$origin = 'http://127.0.0.1:8280'
$s = Invoke-RestMethod -Method Post -Uri "$origin/dcml/native-sessions" `
    -ContentType 'application/json' `
    -Body '{"repository":"continuum:research"}'
$r = Invoke-RestMethod -Method Post -Uri "$origin/dcml/native-cycle" `
    -ContentType 'application/json' `
    -Body (@{
        session_id = $s.id
        message = 'Determine the next reproducible research experiment'
        context = @{ wing = 'research'; mission_id = 'founder-local-mission' }
    } | ConvertTo-Json -Depth 5)
$r | ConvertTo-Json -Depth 9
```

The response contains actual `cycle_id`, `strategy`, `prediction`, `counterfactual`, `evidence_id`, `state_revision`, recall counts, and `inference_mode: native_structured_policy`. It marks `language_generation_performed:false` and `external_outcome_verified:false`. A strategy's projected confidence is **not** measured real-world correctness.

Use five persistent sessions (research, platform, products, ventures, fleet) sharing one native BRAINSTEM identity and memory state. The separate Continuum integration tracks sessions across invocations. Existing `/sessions`, `/chat` and attached models remain compatible.

## Tests

```bash
python -m pytest -q tests/test_native_dcml_continuum.py
python -m pytest -q
```

The targeted tests verify:
- five independent sessions, same native cognitive identity, increasing durable state revisions;
- no external adapter required and no fake natural-language generation;
- actual native prediction/counterfactual, evidence and experience records;
- recall before adding a fresh experience;
- state surviving service restart;
- no false external outcome or automatic learning promotion;
- nonnative session and malformed input rejection.

This is the **existing native symbolic/stateful DCML inference pathway** exposed through its own API. Open-ended English model generation remains a distinct optional workload. No independent production efficacy benchmark is asserted.
