# External frontier benchmark blockers

Status as executed in this repository environment:

| Benchmark | Adapter | External run | Blocker |
|---|---|---|---|
| MMLU-Pro | Implemented | NOT_CONFIGURED | Official dataset/evaluator command and attached model absent |
| GPQA Diamond | Implemented | NOT_CONFIGURED | Dataset access terms, official evaluator, and model absent |
| LiveBench | Implemented | NOT_CONFIGURED | Official dataset/evaluator and model absent |
| ARC-AGI-2 | Implemented | NOT_CONFIGURED | Official data/evaluator and model absent |
| BFCL | Implemented | NOT_CONFIGURED | Official evaluator/data and approved function model absent |
| GAIA | Implemented | LICENSE_REQUIRED | Dataset approval plus browsing environment absent |
| GAIA2 | Implemented | LICENSE_REQUIRED | Official environment and access absent |
| BrowseComp | Implemented | NOT_CONFIGURED | Official evaluator/data, live-web policy, and model absent |
| SWE-bench Verified | Implemented | NOT_CONFIGURED | Official instances, Docker evaluator, and model absent |
| SWE-Lancer Diamond | Implemented | NOT_CONFIGURED | Official dataset/container access and model absent |
| LiveCodeBench | Implemented | NOT_CONFIGURED | Official evaluator/data and model absent |
| OSWorld 2.0 | Implemented | LICENSE_REQUIRED | Gated task package and official VM absent |

Internet metadata verification was attempted using the web search integration and official Git remotes, but neither returned authenticated/usable results in this container. Consequently versions remain truthfully labeled `official-current` rather than inventing a commit or release. Operators must freeze exact official commits and dataset hashes before any reproducible run.

No external score, attached-model baseline, DCML lift, cost, latency, or publication-eligible result exists from this pass. The deterministic test evaluator is marked `TEST_ONLY`, `NONSTANDARD`, and non-official; it validates orchestration and artifact production only.
