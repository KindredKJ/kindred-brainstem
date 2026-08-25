# Brainstem AGI Foundation

This package installs three coordinated foundations:

1. Governed cognitive cycle
2. Durable local memory
3. Measurable benchmark and validation harness

Safe self-improvement is proposal-only. Brainstem can write an improvement
proposal into `state\improvement-proposals`, but it cannot silently modify the
cryptographically locked core.

## Run a cognitive cycle

```powershell
& ".\Invoke-BrainstemAGI.ps1" `
  -Objective "Review Brainstem's current architecture and identify the next highest-value upgrade."
```

## Run the complete validation suite

```powershell
& ".\tests\Invoke-BrainstemAGITests.ps1"
```

## Important boundary

Passing these tests verifies that the foundation is installed and internally
consistent. It does not establish human-level general intelligence. Open-domain
AGI status still requires validated model reasoning, broad transfer benchmarks,
long-horizon autonomy testing, reliability testing, and independent evaluation.