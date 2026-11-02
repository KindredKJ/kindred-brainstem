# Kindred Labs: Rank-One Frontier Evidence Protocol

Status: research infrastructure, **not** a #1 result. Date: 2026-11-02.
Founder identity: Kindred Jermaine Cox. This document is part of the established
`brainstem.benchmarks` system; it must not create a second benchmark authority.

## Public claim contract

**Claim we want to earn, stated precisely:**

> "Kindred <exact system name + provider attribution> ranked #1 in <exact
> external benchmark, version, dated official leaderboard, rules and split> at
> <score>, <cost/task>, with independently reproducible execution evidence."

Never collapse this into "Kindred is #1 in AGI" or "Kindred has AGI" without
entirely separate objective scientific evidence and broad peer consensus.

A single local benchmark, signed JSON file, unit test, customer purchase,
prototype, or internally maintained ranking is **not** evidence of worldwide
AGI leadership.

## Why ARC-AGI-3 is a top priority

ARC-AGI-3 evaluates exploration, modeling, goal-setting, planning and
execution in previously unseen interactive environments. It is distinct
from ARC-AGI-2's static tasks. Its official harness, SDK, action-efficiency
scoring and developer scorecards provide a more substantive test of the
Kindred¤ persistent-state and causal-world-model research program.

**Official competition facts as of 2026-11-02:**
- 2026 ARC-AGI-3 submissions are due 2026-11-02.
- The paper deadline is 2026-11-08 and results are announced 2026-12-04.
- Competition execution is offline with no internet / external model API
  access. An attached hosted model is not a qualifying competition entry.
- The organizer requires open-sourcing eligible competition methods.
- Developer scorecards and independent Kaggle competition results have
  different evaluation semantics. Do not mix or mislabel them.

Official references:
- https://arcprize.org/competitions/2026
- https://arcprize.org/competitions/2026/arc-agi-3
- https://github.com/arcprize/arc-agi-3-benchmarking
- https://github.com/arcprize/docs/blob/main/methodology.mdx

## Reuse the real official environment

An **operator with official credentials** can run the official open-source
benchmarking harness. These commands inspect and run the upstream harness,
NOT the Kindred fork or a simulated task:

```powershell
git clone https://github.com/arcprize/arc-agi-3-benchmarking.git
Set-Location arc-agi-3-benchmarking
git rev-parse HEAD
uv sync
uv run main.py --list-games
uv run main.py --list-configs
```

Set `ARC_API_KEY` and any actual provider credentials in the local private
environment (never commit them). For a **developer evaluation**, an operator
can use a listed model config:

```powershell
uv run main.py --game=ls20
```

This tests the official sample/default agent. It does not test native
Kindred¤ unless Kindred's actual agent is correctly integrated into the
official harness and independently measured. The website's official scorecard
or competition record is the authority for results, not CLI exit success.

The new BRAINSTEM registry entry `arc-agi-3` is `NOT_CONFIGURED` until
`KINDRED_BENCHMARK_ARC_AGI_3_CMD` explicitly invokes an approved evaluator.
Do not put passwords or key values in the command itself. The BRAINSTEM
external runner's command environment is allow-listed, so approved
credential variables, sandbox boundaries and exact official evaluator commits
must be verified. Scoring integration requires adapting official ARC-AGI-3
output to this repository's `task_success_rate` contract; the registration
alone is not a working evaluation.

## Cryptographic snapshot comparison (new code)

`python -m brainstem.benchmarks.rank_proof` accepts a raw detached Ed25519
signature of the **exact original JSON bytes**, a PEM-encoded signer public
key, and a complete ARC-AGI-3 leaderboard snapshot following this contract.
It does no network requests and never changes a provider account.

Private/untrusted input JSON contract:

```json
{
  "schema_version": 1,
  "benchmark": "arc-agi-3",
  "benchmark_version": "2026",
  "issuer_name": "Name of actual issuing body",
  "board_type": "PUBLIC_PROVISIONAL",
  "evaluated_at": "2026-11-02T10:00:00Z",
  "source_url": "https://arcprize.org/leaderboard",
  "metric": "score_percent",
  "score_direction": "higher",
  "dataset_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "evaluator_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "protocol_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "conditions_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "total_entries": 2,
  "rows": [
    {
      "system_id": "kindred-test",
      "system_name": "Kindred + named provider test configuration",
      "provider_model": "EXAMPLE MODEL",
      "configuration": "BRAINSTEM_STATIC",
      "conditions_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "score": 50
    },
    {
      "system_id": "competitor-test",
      "system_name": "Example comparison system",
      "provider_model": "EXAMPLE MODEL",
      "configuration": "ATTACHED_MODEL_DIRECT",
      "conditions_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "score": 49
    }
  ]
}
```

All digests, scores, identities and metadata above are **illustrative and not
a real leaderboard**. Never publish that JSON as a benchmark result.

Run using *actual verified third-party-issued* `board.json`,
`board.sig` (64 raw signature bytes), and `issuer.pub` (PEM):

```powershell
python -m brainstem.benchmarks.rank_proof --snapshot .\board.json --signature .\board.sig --public-key .\issuer.pub --system-id kindred-test --output .\rank_report.json
```

The CLI can verify only:
1. The supplied key signed the exact supplied bytes.
2. JSON fields are well formed and score values fall within expected bounds.
3. Every participant declares the same evaluation-conditions digest.
4. The target is actually present, its ordinal rank, and tie status.

It **cannot** verify:
- That the public key truly belongs to ARC Prize/Kaggle or an impartial evaluator.
- That the JSON is the authentic official leaderboard or includes every entry.
- That a declared hash matches real evaluator code or actual test data.
- That scores are honest or reproducible.
- That the named model is Kindred-native rather than a wrapped provider.
- That any worldwide #1 or AGI claim is justified.

It reports `authority_independently_verified=false`,
`external_score_independently_reproduced=false`,
`global_number_one_claim_supported=false` even for a signed rank-one
snapshot. This is deliberate: a self-signed snapshot is not a #1 proof.

## Independent publication process

1. **Freeze sources**: exact official evaluator Git commit, dataset
   license and digest, hardware/compute budget, task split, action policy,
   dependency lockfile, runtime/container SHA, model checkpoint SHA.
2. **Separate model attribution**: native Kindred model vs
   BRAINSTEM + provider/model. Do not transfer scores between systems.
3. **Run official evaluator** on the genuinely held-out partition; retain
   raw run artifacts privately, signed task receipts, failure traces and
   operator interventions. Follow contest rules.
4. **Compare against all eligible entries** on the same dated leaderboard,
   same harness, costs, tool access and task policy. A provisional public
   first place is not a final private-evaluation win.
5. **Reproduce** in an independent runner maintained by an independent
   evaluator; publish error bars where repetitions make sense and measure
   cost per successful task.
6. **Acquire authentic authority**: source key fingerprint obtained directly
   from the official maintainer via an authenticated independent channel,
   immutable full snapshot and detached signature. The JSON auditor's
   source URL is only a declaration and does not perform this step.
7. **Release responsibly**: publish exact scoped claim, methodology,
   official ranking URL, model/provider attribution, immutable evidence
   references, limitations, expiration/last-check time and subsequent
   revisions. Never release hidden test answers or customer secrets.

## Definition of truly front-rank competitive research

- Official benchmark rank and score, measured at a given date.
- Reliability across independent runs and out-of-distribution tasks.
- Compute and dollar cost per solved task, with documented hardware.
- Material lift attributable to original Kindred architecture via ablations.
- Security, safe autonomous operation, privacy and recovery demonstrations.
- Paid, fulfilled external products with independent third-party evidence.
- Open, reproducible research accepted by external peers.

A "best AI lab" claim spans many contested dimensions and has no globally
recognized single leaderboard. Publish category-specific leadership first
and treat a general #1 claim as a longer-term reputation objective.

## Audit priority

Immediate: qualify an offline native-compatible ARC-AGI-3 agent and inspect
the official evaluation submission process. Next: build real paired
BRAINSTEM-vs-direct-provider evaluations under identical conditions, plus
NTSA-X/Kindred¤ native ablations. Keep public claims at
**RESEARCH_IN_PROGRESS** until real external evidence exists.

No live Kaggle submission, production deployment, customer charge,
domain change, or external leaderboard result was performed by this PR.
