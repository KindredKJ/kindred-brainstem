# Kindred Causal Mesh — bilateral transcripts and signed Merkle folding

Founder / authorship: Kindred Jermaine Cox / Kindred Labs.

## What was implemented

`brainstem/fabric/causal_mesh.py` defines two-party Ed25519 signed records, a monotonic local peer transcript, and verifiable conflicting signed-record evidence.

`brainstem/fabric/proof_folder.py` validates and aggregates consecutive records into signed Merkle summary envelopes, and can aggregate the signed child envelopes again into a second-layer super-envelope. The aggregate commits to a trusted signer, sequence range, initial/final chain heads, record count, signed micro-unit totals, integer nanjoule totals, and Merkle root. Its leaf inclusion witness is logarithmic in record count.

`scripts/benchmark_causal_mesh.py` generates synthetic bilateral records, commits them to the counterparty's in-memory transcript, folds them into configurable batches, exercises signed conflicting records, and benchmarks envelope verification and **two-level** Merkle inclusion separately. Results identify Python/platform and report local measurements; they are not estimates.

## Critical proof distinctions

**This is not a ZK proof and not recursive cryptographic proof folding.** It is repeated Merkle aggregation of **signer-attested claims**. The signed super-envelope is constant-size in record count, but verifying the claims inside it requires trusting the aggregator to have performed the upfront individual checks, retrieving and verifying underlying records, or replacing this mechanism with a real succinct proof system. A signature alone does not prove the committed sum, that the record chain was checked, or that financial transfer occurred.

Envelope validation requires an explicit `trusted_aggregator_pub_hex`; self-signed envelopes with unknown public keys are not trusted evidence. An inclusion witness must be supplied with both the record's actual `commitment_hash()` and the signed envelope's trusted root. For nested proofs the verifier must check the batch envelope signature and membership **and** the batch envelope's inclusion in the super-envelope.

`EquivocationFraudWarrant` retains both independently signed conflicting records and can be verified from those records. It shows a signed local sequence conflict, not a global double-spend proof, consensus finality, or legal fraud adjudication.

The benchmark's `value_delta_micro_units` and energy inputs are deliberately **synthetic**. It does not execute live EMIT tasks, transfer real funds or measure physical power. Power values are summed as integer nanjoules to avoid accumulating floating-point errors. A standalone causal mesh and the existing PoECL worker receipts are **not yet wired into a real settlement or payment rail**.

## Run on Windows PowerShell 7

Use the already verified isolated BRAINSTEM checkout:

```powershell
$work = Join-Path $env:TEMP 'Kindred-Workforce-E2E-2a303bebd9e647609f8bdcee2cfa21c7'
$brain = Join-Path $work 'BRAINSTEM'
git -C $brain pull --ff-only
if ($LASTEXITCODE -ne 0) { throw 'BRAINSTEM checkout update failed' }
$python = Join-Path $brain '.venv\Scripts\python.exe'
& $python -m pytest -q (Join-Path $brain 'tests\test_causal_mesh.py')
if ($LASTEXITCODE -ne 0) { throw 'Causal mesh regression tests failed' }
& $python (Join-Path $brain 'scripts\benchmark_causal_mesh.py') --records 100000 --batch-size 1000 --output (Join-Path $work 'causal_mesh_100k.json')
if ($LASTEXITCODE -ne 0) { throw '100,000-settlement benchmark failed' }
```

The earlier system-wide `python` executable on this Windows system resolved to 3.11, whereas this project requires Python 3.12 or newer; the existing BRAINSTEM virtual environment is preferable.

To run an inexpensive check first:

```powershell
& $python (Join-Path $brain 'scripts\benchmark_causal_mesh.py') --records 1000 --batch-size 100 --repeat-verification 100
```

## Unverified bounds

Do not claim `<1ms` edge verification or `100,000` live settlements without running and publishing the benchmark logs. The aggregate signature verification is constant work, while a nested Merkle inclusion proof takes O(log N) hashes. Building the fold and verifying each record is O(N). In particular, **no consensus or regulatory settlement finality** arises from two local signing keys.
