# External frontier benchmark evaluation

## Boundary and attribution

External frontier evaluation is a separate subsystem from `INTERNAL_DCML_EVALUATION`. Internal tests establish whether approval, learning, rollback, persistence, consolidation, calibration, and transfer mechanisms function. They are never entered in the external leaderboard. `EXTERNAL_FRONTIER_BENCHMARK` records third-party task performance only.

Every external manifest names the evaluated system and refuses to attribute an attached provider's output to BRAINSTEM alone. Supported configurations are `ATTACHED_MODEL_DIRECT`, `BRAINSTEM_STATIC`, `BRAINSTEM_DCML_PRE_LEARNING`, `BRAINSTEM_DCML_POST_LEARNING`, `BRAINSTEM_DCML_ROLLBACK`, and `BRAINSTEM_NATIVE_ONLY`. Native-only execution is `NOT_CONFIGURED` where no native task executor exists.

## Registry and truthful readiness

The registry describes MMLU-Pro, GPQA Diamond, LiveBench, ARC-AGI-2, BFCL, GAIA, GAIA2, BrowseComp, SWE-bench Verified, SWE-Lancer Diamond, LiveCodeBench, and OSWorld 2.0. Registry presence means only that an adapter contract exists. No dataset is downloaded automatically. An adapter becomes `AVAILABLE` only after its official evaluator command is explicitly configured. Dataset, license, gated-package, container, browser, or VM requirements remain `DATASET_REQUIRED`, `LICENSE_REQUIRED`, `ENVIRONMENT_REQUIRED`, or `NOT_CONFIGURED` as applicable.

The environment used for this pass had no configured evaluator, dataset, attached frontier model, gated environment, or verified network access. Therefore no external smoke or full score was produced. This is a blocker, not a zero score.

## Seal and contamination controls

`kindred benchmark seal` writes a restrictive-permission, process-independent seal. External execution refuses to start while unsealed. While sealed, `StateStore.execute` blocks canonical writes to memory, experiences, beliefs, learning proposals, datasets, concepts, skills, and missions. Evaluators run in disposable `0700` temporary directories. The child environment is allow-listed rather than inheriting credentials.

Runs also require benchmark-maintainer-derived contamination signatures. Scanning covers questions, answer keys, distinctive substrings, canaries, reference patches, evaluator logic, hidden-test artifacts, prior answers, and solution repositories. Findings store hashes rather than the matched content. A finding marks the run `CONTAMINATED`, writes exclusion artifacts, and prevents leaderboard inclusion. A clean scan means only `NO_KNOWN_CONTAMINATION_DETECTED`; public-pretraining and paraphrase risk remain explicit.

## Tool fidelity, learning freeze, and reports

The official evaluator must emit a JSON result. Browsing, functions, containers, and VMs are declared by benchmark policy. Unless evaluator integrity, dataset hash, and tool-policy fidelity are explicitly verified, results are `NONSTANDARD` and not official. The harness never promotes benchmark learning. Development-partition learning must occur before a held-out run, produce a frozen approved checkpoint, and remain disabled throughout evaluation.

Each completed run writes:

- `manifest.json`: exact Git commits, checkpoint, provider/model identity, benchmark version, hashes, tools, inference settings, budgets, hardware, OS, seed, and timestamp;
- `results.json`: official and DCML metrics plus repeated-run statistics;
- `contamination.json`: controls, findings, and residual risk;
- `attribution.json`: ablation dimensions labeled associative, not causal;
- `report.md`: human-readable status and limitations.

Publication remains `INTERNAL_ONLY` unless license compliance, contamination control, complete environment, reproducibility, frozen commit/checkpoint, evaluator integrity, hidden-test protection, learning freeze, rerun, and signed founder approval all pass.

## Commands

```powershell
kindred benchmark list
kindred benchmark inspect mmlu-pro
kindred benchmark setup mmlu-pro
kindred benchmark doctor mmlu-pro
kindred benchmark seal
kindred benchmark seal-status
kindred benchmark contamination-scan mmlu-pro --signatures .\approved-signatures.json
kindred benchmark run mmlu-pro --configuration ATTACHED_MODEL_DIRECT --provider Codex --model <reported-model> --signatures .\approved-signatures.json
kindred benchmark run-suite frontier-core                 # dry-run
kindred benchmark run-suite frontier-core --execute       # explicit execution
kindred benchmark ablate mmlu-pro                         # dry-run
kindred benchmark compare <run-a> <run-b>
kindred benchmark contamination-report <run-id>
kindred benchmark report <run-id>
kindred benchmark export <run-id>
kindred benchmark leaderboard
kindred benchmark unseal
```

Full suites are never launched implicitly. `run-suite` and `ablate` are dry runs without `--execute`.
