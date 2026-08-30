# BRAINSTEM Release Gate

Use this checklist for every prerelease and stable BRAINSTEM publication.

## Identity

- [ ] Canonical repository is `KindredKJ/kindred-brainstem`.
- [ ] Candidate commit exists on GitHub and its SHA is recorded.
- [ ] `pyproject.toml`, build backend, `brainstem.__version__`, CLI output, wheel metadata, tag, and release name agree.

## Verification

- [ ] Targeted regression tests pass.
- [ ] Exactly one final full test suite passes after the last code change.
- [ ] `git diff --check` passes.
- [ ] Wheel/package build passes.
- [ ] Clean isolated install passes.
- [ ] Installed `kindred --help` smoke test passes outside the repository checkout.
- [ ] CI/checks are green for the exact candidate SHA.
- [ ] Final code review is run against the exact candidate SHA.
- [ ] No unresolved P1/P2 production blocker remains.

## Governance and safety

- [ ] Founder/governance authorization paths are cryptographic and fail closed.
- [ ] Privacy and cross-session isolation tests pass.
- [ ] Learning/evidence approval and rollback gates pass.
- [ ] State, audit, idempotency, concurrency, and Port Zero transition tests pass.

## Publication

- [ ] `CHANGELOG.md` is updated.
- [ ] Release notes distinguish verified capability from planned capability.
- [ ] Tag follows `vMAJOR.MINOR.PATCH[-prerelease]`.
- [ ] Published tags are immutable.
- [ ] GitHub Release points to the exact tag and SHA.
- [ ] Release artifacts and checksums are attached or reproducibly obtainable.

## Stable-only gate

For `v0.1.0` or any later stable release:

- [ ] No alpha/beta/RC qualifier remains in package metadata.
- [ ] Production deployment/rollback procedure has been exercised or independently verified.
- [ ] Release decision is explicitly recorded as `MERGE READY / RELEASE READY`.
