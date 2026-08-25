# Brainstem Intelligence Runtime v2

The runtime adds governed local/cloud model routing, structured validation,
comparative reasoning, critique, synthesis, evidence-derived confidence,
memory isolation, checkpointed tasks, external-action approvals, and a
tamper-evident audit chain.

Provider status:
```powershell
& ".\Get-BrainstemProviderStatus.ps1" -Probe
```

Architectural audit:
```powershell
& ".\Invoke-BrainstemAGI.ps1" -Objective "Audit Brainstem and identify the next highest-value AGI capability gap." -MaximumProviders 3 -AsJson
```

Long task:
```powershell
& ".\Invoke-BrainstemLongTask.ps1" -Objective "Create an evidence-backed Brainstem capability map." -AsJson
```

A successful live audit reports `COMPLETED_MODEL_BACKED`. The runtime does not
claim AGI merely because installation or scaffold tests pass.