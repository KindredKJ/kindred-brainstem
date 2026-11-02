# Kindred Labs AGI Frontier Program — evidence-led launch plan

Date: 2026-11-02. Founder: Kindred Jermaine Cox. Status: **engineering proposal**, not an AGI achievement, production deployment, or financial certification.

## Core proposition

Kindred Labs should compete on **independently measured autonomous execution, persistent cognition, causal prediction, and commercially useful outcomes**, not on an unqualified claim to have reached AGI.

Preserve Kindred¤ / NTSA-X as an original *research track* distinct from the provider-backed BRAINSTEM *product track*. When BRAINSTEM uses a third-party LLM, label benchmarks and demonstrations `BRAINSTEM + provider + model`; never attribute an attached model's intelligence to the native architecture alone.

## OpenClaw architecture comparison (official docs, reviewed November 2026)

| Capability | OpenClaw | Kindred evidence / gap | Disposition |
|---|---|---|---|
| Messaging channels and shared gateway | Documented multi-channel gateway | BRAINSTEM loopback FastAPI runtime; no comparable channel gateway verified | Build an isolated gateway adapter, not a gateway rewrite |
| Tools, plugins, repeatable skills | Documented tools/plugins/skills | BRAINSTEM adapters and Kindred Cloud provider registry | Define narrow typed capabilities and per-tool authorization |
| Sessions and memory | Multi-agent sessions and routing documented | BRAINSTEM SQLite sessions, evolving DCML candidate memory | Retain typed memory and provenance; prove cross-session task benefit |
| Scheduling and webhooks | Documented | Kindred ecosystem has various workflow tools, no interoperable end-to-end live proof established here | Implement a single auditable commercial workflow first |
| Autonomous software delivery | Tool and agent execution workflows | App Factory architecture and cloud components, unverified customer release | Demonstrate one Git commit to independent staging to real payment |
| Native novel cognition | No evidence this is the purpose of OpenClaw | NTSA-X recurrent/paired-orbit and Kindred¤ research concepts | Publish hypotheses and independent ablations, not AGI claims |

Source: https://docs.openclaw.ai/ ; https://docs.openclaw.ai/tools

## Measurable milestones

### Track A — paid autonomous product operations (next 30 days)

1. Preserve all existing production routes. Use separate commercial staging, data stores, secrets, tenant space and deploy credentials.
2. Select one sellable product: **Kindred Cloud Storage + Sites**. Define a narrow paid pilot with real customer terms, measurable capacity and support obligations.
3. Capture one reviewed agent trace linked to a specific Git SHA and release metadata. Human interventions must be counted explicitly.
4. Expose `https://<approved-host>/.well-known/kindred-release.json` on the isolated commercial staging deployment, returning real `{"commit":"<40-hex-SHA>","run_id":"<run-id>"}` values from its deployed release, not hardcoded claims.
5. Accept one genuine Stripe **live-mode** USD PaymentIntent with `metadata.kindred_run_id` matching the release. A succeeded intent establishes a Stripe payment record, not bank settlement or positive margin.
6. Run `python -m brainstem.benchmarks.commercial_pilot <local-manifest.json>` using read-only credentials, then independently inspect provider records. Preserve private customer and receipt details outside Git.
7. Before wider launch, demonstrate tenant isolation, backup/restore recovery, TLS, pricing and cost, support workflow, and explicit hosting separation.

Commercial pilot manifest schema (JSON, private evidence only):

```json
{
  "schema_version": 1,
  "run_id": "kindred-pilot-20261102",
  "repo": "KindredKJ/kindred-cloud",
  "commit": "0123456789abcdef0123456789abcdef01234567",
  "deployment_host": "commercial-staging.kindredlabs.ai",
  "stripe_payment_intent": "pi_123456789",
  "agent_trace_file": "private/trace.jsonl",
  "agent_trace_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

The above is a **schema illustration**, not a real receipt. Run with `KINDRED_PILOT_ALLOWED_HOSTS` specifying exactly the inspected hostname, `STRIPE_SECRET_KEY` holding a read-capable live key, and `GITHUB_TOKEN` when the repository is private. The verifier only performs HTTPS GETs and local SHA-256 verification. Failure returns exit 2. No keys or raw customer details are written to its report.

**Verification limitation:** The release endpoint is operator-controlled metadata and may claim a commit without proving its deployed bytes. A SHA-256 hash validates only a local trace's integrity, not whether the agent acted autonomously. Matching Stripe data proves a provider payment record, not delivered service, genuine customer usage, profitability, or bank settlement. Obtain independent deployment attestations, observed customer use and financial reconciliation before making stronger claims.

### Track B — external reasoning and autonomy benchmarks (30–60 days)

Reuse existing `brainstem.benchmarks` registry, runner, sealing, contamination and publication controls. Do **not** duplicate the harness.

- ARC-AGI-2: abstract rule generalization, official evaluator, cost per task solved.
- BFCL: tool-call correctness, tool selection and leakage testing.
- GAIA/GAIA2 and OSWorld: externally graded agentic work where access is legally available and authorized.
- Coding: prefer a current validated evaluation with fresh, privately held-out repository tasks and independent adjudication. **Do not treat SWE-bench Verified as frontier-grade evidence**: OpenAI's February 2026 audit and Epoch's September 2026 review found major contamination and grading issues. SWE-bench Pro also has a documented 2026 test-quality audit; independently audit selected tasks before reporting.
- All comparative studies: identical tasks, models, tool budgets, compute budgets, repetitions and confidence intervals; compare base attached model versus BRAINSTEM-managed model, identify human interventions and actual cost.
- Native-only scores must be from the native architecture running the workload; no inherited provider score.

Sources:
- https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/
- https://openai.com/index/separating-signal-from-noise-coding-evaluations/
- https://arcprize.org/

### Track C — original Kindred¤ research (60–90 days)

1. Freeze baseline kernel/model/runtime commits and licensed datasets.
2. Establish token/byte-stream, recurrent X/Y/Z, recall-before-inference and causal-world-model ablations.
3. Compare accuracy, latency, memory retention, generalization to unseen tasks, compute per successful task and error-calibration; report failures as well as improvements.
4. Separate research prototypes from trained foundation-model claims. No model training evidence = no trained-model performance claim.
5. Release reproducible research notes and licensed demos after data, privacy, security, and founder publication review.

## Public positioning and distribution

A defensible headline: **"Kindred Labs builds evidence-governed autonomous AI systems and researches persistent, non-Transformer cognition."**

Publish a research index containing architecture, reproduction instructions, declared model attribution, honest benchmark reports, verifiable release receipts and a developer SDK. Present benchmark scores only when official evaluator integrity and independent reproduction are established. Recruit pilot customers from a specific service offering; track qualified leads, activated pilots, paid conversions, gross margin, uptime and customer retention.

Do not claim: "AGI achieved", "frontier-leading", "world's best", "fully autonomous", or "revenue-generating" unless that exact claim has independent supporting evidence.

## Decision log / integration rule

- No merging into `main`, production redeploy, DNS mutation, secret movement, financial charge, or public press release is part of this change.
- This branch adds a provider-read-only evidence contract and unit tests to the existing BRAINSTEM benchmark package.
- GitHub PR checks and actual live reconciliation are separate evidence stages. Mocked unit tests **never** count as revenue or customer proof.
- Next integration issue belongs in `kindred-cloud`, not a parallel duplicate cloud runtime.
