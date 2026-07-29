# KINDRED BRAINSTEM CLI

**BRAINSTEM: From Signal to Infrastructure.** Founded by Kindred Jermaine Cox and originated from Kindred Labs.

The canonical executable is `kindred` (`brainstem`, `bstem`, and `kbs` remain
convenience entry points). Open the governed runtime with `kindred`, attach a
model with `kindred attach <model>`, use `kindred codex --here` for repository
aware Codex sessions, or verify all local cognitive planes with `kindred awaken`.

Attachments are local, isolated, persistent session records. Observations enter
candidate learning state and production modification remains blocked; the CLI
does not silently retrain an attached model.

## What BRAINSTEM is
BRAINSTEM is a persistent cognitive model whose native DCML mechanism converts signals into governed, evidence-ledgered cognitive and infrastructure results. The local runtime serves the model; it does not define BRAINSTEM's intelligence. It does not count plans, generated text, or hype as success.

## Existing repo status
The repo preserves the Kindred Revenue Stack Engine (KRSE) and extends the doctrine into a result-only reality execution, audit, approval, memory, backprop, PlugCore, and corporate transition layer.

## Result-Only Doctrine
Result levels run from `0 = idea` through `10 = durable_market_result`. Level 4 requires local verified artifacts. Level 5 requires external evidence. Unsupported claims are downgraded.

## Beyond Local / External Impact
External outcomes are recorded in `data/external_outcomes.jsonl`. Mock outcomes are explicitly marked and do not prove launch, revenue, or human use.

## KRSE
KRSE remains the native revenue planning engine. It defines offer, price, payment path, payout, margin, reserve, and reinvestment logic without processing real payments.

## Founder Approval Plane
High-impact actions require explicit founder approval from Kindred Jermaine Cox. Silence never approves. The local approval server binds to `127.0.0.1` by default.

## PlugCore
PlugCore scans the current host and writes local host/capability/resource reports.

## Max Safe Potential
The planner estimates compute, network, storage, safety, permission, and result-execution scores while keeping hard actions approval-gated.

## Model Runtime Layer
The model runtime uses mock/rule adapters by default. No paid APIs, external keys, or heavy training dependencies are required.

## Reality Attention
Reality Attention prioritizes the blockers most relevant to the next verified result, especially evidence gaps.

## Associative Memory
Local associative memory stores and recalls Kindred/BRAINSTEM structures from partial phrases and tags. It does not invent memory.

## BackProp Engine
Reality backprop turns failures, missing evidence, approvals, denials, and result gaps into learning records. Model backprop is planning-only in v1.

## Global Asset + Revenue Audit Engine
The Global Audit Engine inventories founder assets, entities, revenue, liabilities, IP, domains, and repositories for audit support and professional review.

## Corporate Transition Engine
The Corporate Transition Engine maps BRAINSTEM as the proposed public umbrella while preserving Kindred Labs lineage. It does not claim legal consolidation.

## CPA / Legal / Tax Review Packets
Reports include: "This system organizes founder-provided and publicly discoverable records for audit, planning, and professional review. It is not legal, tax, accounting, investment, or financial advice."

## Claim Guard
Protected claims such as launched, revenue-generating, tax-ready, legally consolidated, and world-class are downgraded unless evidence exists.

## Earth-Class Validation
Earth-class validation evaluates real-result, external-result, reliability, lineage, approval, audit, and transition evidence. It never verifies “best on Earth.”

## How to run the full local reality loop
```bash
pip install -e ".[dev]"
pytest
brainstem health
brainstem reality products/moneyback_scan.yaml
brainstem plugcore scan
brainstem awareness
brainstem claims moneyback_scan --claim launched --claim revenue_generating --claim tax_ready
```

## How to run the founder audit loop
```bash
brainstem audit start --purpose "global founder asset and revenue audit"
brainstem audit scan-local
brainstem audit inventory
brainstem audit report
brainstem audit cpa-pack
brainstem transition report
```

## What is internal-only and never externally packaged
Founder approvals, private audit imports, local ledgers, raw evidence, private financial CSVs, and internal governance endpoints are internal-only. BRAINSTEM v1 performs no real payments, tax filings, legal filings, public launches, cloud deployment, or asset transfers.

## Runtime vertical slice (0.1.0-alpha)

The CLI now acts as a client to a loopback BRAINSTEM runtime service. Start it
with `kindred runtime start`, inspect actual probes with `kindred runtime status`,
and then use `kindred shell`. Canonical session, message, evidence, learning, and
audit state is stored in SQLite under `~/.kindred`; repository-local `.kindred`
state contains the active session pointer.

No inference model is bundled. H^ and Codex remain `NOT_CONFIGURED` until their
real runtimes are present and pass health probes. An explicitly configured
OpenAI-compatible endpoint can provide inference; model failures never silently
fall back. See [the current-state assessment](docs/CURRENT_STATE_ASSESSMENT.md)
and [architecture](docs/ARCHITECTURE.md) for verified scope and limitations.
