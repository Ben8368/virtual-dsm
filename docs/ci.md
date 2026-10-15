# CI and dependency updates

`CI` runs on every push to `master`, every pull request (including Dependabot),
and manual dispatch. It needs no repository secrets. The workflow exposes six
checkable jobs (repository traffic light / 6/6):

1. **Docs governance** — `scripts/governance-docs-check.py` and commit-hook regression.
2. **Lint** — Bash syntax, ShellCheck, Hadolint, JSON/YAML parsing and Actionlint.
3. **Synthetic regression tests** — platform, acquisition, guest, image and installer checks without DSM downloads.
4. **QEMU patch apply** — pristine upstream v8.2.2 clean application of `patches/qemu/8.2.2`.
5. **Research smoke** — `research/arm64/tests/smoke.sh`.
6. **Production image build** — native Ubuntu 24.04 amd64 and arm64 Docker builds, then emulator, shared-library, Python import, default x86 argv and [synthetic DC ZVA](../tests/qemu-dcz/README.md) checks against each image's actual patched QEMU.

Human `🚦 Audit Report` review remains required for product source changes and is
not replaced by a green CI aggregate.

The synthetic tests do not download or redistribute DSM payloads. CI does not
prove full DSM boot, ARM KVM compatibility or Surveillance Station acceptance;
those still require the separately documented official-PAT/hardware checks.
BuildKit caches are separate per host architecture. New commits cancel obsolete
CI runs; release runs are serialized and never canceled by newer releases.
Actions are pinned to commits and refreshed by Dependabot.
The installer fixture runs with `sudo` on the disposable runner so tar can
restore numeric ownership and special files without fakeroot interception.

## Publishing

Run `Publish image` from `master` with a version such as `1.0.0`. It validates the
version, reruns all CI checks, builds natively, uploads each image to GHCR by
digest, verifies it, then creates the multi-platform version and `latest` tags.
For this repository the image is `ghcr.io/ben8368/virtual-dsm`. Only publishing
jobs receive `packages: write`; the repository's `GITHUB_TOKEN` is sufficient.
Existing version tags can be overwritten, so use a new version for each release.
No Docker Hub account, personal token, version variables, GitLab mirror or mail
server is required. Usage examples target this independently maintained project's
GHCR image. Publish the first image before using those examples; until then,
build from source with `compose.local.yml`. See the README's origin statement
for attribution to the original project.

`Docker Hub description` is optional. Configure all three repository secrets
`DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` and `DOCKERHUB_REPO` to enable README sync.
When any is missing, the workflow reports the skipped sync and succeeds.
This workflow only updates the description; releases publish to GHCR.

## Dependabot

Dependabot checks GitHub Actions, Docker base images and `requirements.txt`
weekly on Monday at 09:00, 09:15 and 09:30 Asia/Shanghai respectively. Version
updates have a seven-day cooldown and bounded open PR counts. Actions and Python
minor/patch updates are grouped per ecosystem; major upgrades and Docker image
updates stay separate for review. All PRs run CI; there is no automatic merge.
Security alerts and security update PRs are enabled in repository settings.
Security updates are not delayed by the version-update cooldown.

`requirements.txt` is shared by the production image and synthetic test fixtures.
The QEMU source version is intentionally pinned to 8.2.2 because the patch series
checks that exact upstream commit; upgrade its source, patches and contract
checks together. Debian packages are supplied by the base distribution and are
outside Dependabot's pip/Docker manifest updates. The inherited Renovate and
external PR-review workflows were removed to avoid duplicate bots and unrelated
upstream automation.
