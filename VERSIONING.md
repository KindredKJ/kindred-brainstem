# Kindred BRAINSTEM Versioning Policy

## Canonical repository

`KindredKJ/kindred-brainstem` is the authoritative source repository for Kindred BRAINSTEM.

Do **not** create a new repository for each software version. BRAINSTEM versions are represented by Git commits, tags, GitHub Releases, package versions, and release branches inside this repository. Separate repositories are reserved for genuinely separate products, integrations, or forks.

## Version scheme

BRAINSTEM uses Semantic Versioning for public releases and PEP 440-compatible package versions for Python artifacts.

| Release stage | Git tag / GitHub Release | Python package |
| --- | --- | --- |
| Alpha | `v0.1.0-alpha.0` | `0.1.0a0` |
| Beta | `v0.1.0-beta.0` | `0.1.0b0` |
| Release candidate | `v0.1.0-rc.0` | `0.1.0rc0` |
| Stable | `v0.1.0` | `0.1.0` |

Until the production gate is satisfied, the current native-model/DCML line remains prerelease software. A stable `v0.1.0` tag must not be created merely because `pyproject.toml` contains `0.1.0` on an older branch.

## Version source of truth

`pyproject.toml` is the package-version source of truth. The custom build backend must derive or remain synchronized with that version; it must not silently publish a different version.

`brainstem.__version__`, CLI version output, wheel metadata, Git tags, and GitHub Release names must agree with the release being built.

## Branch model

- `main` — protected stable integration branch; only production-gated changes land here.
- feature / fix branches — normal development and PR work.
- `release/<major>.<minor>` — optional stabilization line once a release candidate is being prepared.
- `hotfix/<version>` — urgent patch work based on a released tag.
- `meta/*` — repository governance and release-process changes.

Long-lived version-specific product repositories such as `kindred-brainstem-v2` are prohibited unless BRAINSTEM is intentionally forked into a distinct incompatible product.

## Production release gate

A BRAINSTEM release is eligible for a version tag only when all applicable gates are satisfied:

1. Exact candidate SHA is recorded.
2. All targeted regressions pass.
3. One final full test suite passes.
4. Wheel/package build succeeds.
5. Clean isolated installation succeeds.
6. Installed canonical `kindred` CLI smoke test succeeds outside the repository.
7. CI/checks are green for the exact remote candidate SHA.
8. No unresolved P1/P2 security, governance, correctness, state-integrity, privacy, or release-integrity blocker remains.
9. Founder/release approval is recorded.
10. Changelog entry is complete.

A local-only commit cannot be released. The candidate SHA must exist in this GitHub repository before final review, tagging, or release publication.

## Release lineage

Every release must be reconstructable as:

`GitHub Release -> immutable tag -> exact commit SHA -> CI evidence -> built package metadata -> changelog entry`.

Pre-release tags are immutable once published. If an alpha/beta/RC needs changes, increment the prerelease number rather than moving the existing tag.

## Current line

The active production-hardening work is targeting the `0.1.0` line. The native BRAINSTEM/DCML package currently identifies as `0.1.0a0` on the hardening branch and should remain an alpha until the remote production gate is complete.
