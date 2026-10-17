# Production Integration Phase 4B

## Stage 1 architecture contract audit — 2026-10-17

This records the current build contract before Phase 4B implementation changes.

### Build platform and target platform

- Every Dockerfile stage uses BuildKit's default target platform. There is no
  `FROM --platform=$BUILDPLATFORM` override.
- `arm-qemu-build` receives `TARGETARCH`; `scripts/build-arm-qemu.sh` requires
  it to match `dpkg --print-architecture` (`amd64:amd64` or `arm64:arm64`).
  QEMU v8.2.2 is therefore compiled for the final image's architecture, not
  cross-compiled by a host-platform helper.
- The QEMU target list is always `aarch64-softmmu`: the ARM guest emulator is
  installed as `/usr/local/bin/qemu-system-aarch64` in both host image
  architectures. The QEMU executable itself is built for the host image
  architecture (`amd64` in the amd64 image, `arm64` in the arm64 image); its
  emulated guest target is AArch64. This does not change the default x86 guest
  selection.
- `runtime` inherits `qemux/qemu:7.50` at the target platform. Its inherited
  `qemu-system-x86_64` remains the VirtualDSM x86 guest emulator. The image also
  contains target-platform core utilities, Python, and `qemu-host.bin` from
  the target-platform `qemux/qemu-host:2.06` image.
- `DSM_PLATFORM=virtualdsm` remains the default independently of container
  architecture. `DSM_PLATFORM=rtd1619b` opts into the ARM64 DS124 guest. The
  host image architecture does not select the NAS model.

### Architecture outcomes

| Target image | Build execution | Expected key binaries | Guest policy |
| --- | --- | --- | --- |
| `linux/amd64` | Native amd64 QEMU builder and amd64 runtime base | amd64 `/bin/sh`, Python, core utilities, inherited amd64 `qemu-system-x86_64`, amd64-hosted `qemu-system-aarch64` | Default `virtualdsm` remains x86 QEMU; DS124 ARM guest uses TCG |
| `linux/arm64` | Native arm64 QEMU builder and arm64 runtime base | arm64 `/bin/sh`, Python, core utilities, inherited arm64 `qemu-system-x86_64`, arm64-hosted `qemu-system-aarch64` | Default `virtualdsm` remains x86 QEMU; DS124 ARM guest may use KVM after the runtime probe |

`COPY --from=arm-qemu-build` is safe only while the builder stays on target
architecture. Buildx matrix jobs use native Ubuntu amd64 and arm64 runners; a
cross-platform build on a single host would need an explicit target-platform
builder or a deliberate cross-build design. No such cross-build is currently
implemented.

### Workflow contract and audit limits

- `.github/workflows/arm-qemu-build.yml` builds and loads one target platform
  per matrix entry (`ubuntu-24.04` for amd64, `ubuntu-24.04-arm` for arm64),
  then checks both QEMU version commands, QEMU shared libraries, Python imports,
  the default x86 command, and the production-QEMU DC ZVA fixture.
- `.github/workflows/build.yml` publishes one native-built child image per
  architecture by digest and combines exactly two digests into version/latest
  multi-platform tags. It is a publishing workflow and is not run as part of
  local Phase 4B validation.
- Current image checks do not assert each local image's OCI architecture or
  hash all architecture-sensitive executables. Phase 4B will add or run those
  checks before claiming image validation.
- The open-source image contains QEMU and product code only. DSM PAT and
  extracted proprietary firmware are runtime inputs and must remain outside
  Git, CI artifacts, and image build context.

No production behavior was changed to create this contract. Subsequent Phase
4B changes and evidence are appended below.

## Phase 4B implementation and local evidence — 2026-10-17

### ARM64 production image

- Built from the working tree at base commit `b8e8a7d3eeb336866446c1bc435da79fbe08b82d`
  with `docker buildx build --builder colima-phase4a-kvm --platform linux/arm64
  --no-cache --load -t virtual-dsm:phase4b-arm64 .`.
- Local image metadata: `linux/arm64`, image ID
  `sha256:590d41d176348e106090486365331486e7002c3c12cabec50dddd05f9580d66c`.
- `tests/image-architecture.sh virtual-dsm:phase4b-arm64 arm64` passed. Its
  inspected executable ELF files matched ARM64: `/bin/sh`, Python, both QEMU
  executables, and `/run/host.bin`. Runtime dependency and version checks passed.
- QEMU identity: `qemu-system-aarch64` 8.2.2-dirty, built from pinned QEMU
  v8.2.2 commit `11aa0b1ff115b86160c4d37e7c37e6a6b13b77ea`; production patches
  0001–0004 are applied. ARM QEMU SHA256 is
  `5a33d08beaf0f009a9e305f1f33df9a51a8f66a5d286b6f5c4bdb567d167880a`.
  Inherited x86 QEMU is 11.1.0; its SHA256 is
  `061922ef2487d0c7e33d498755149c687dd4bb752c695bd98f01e4d7c6f63add`.
- The final ARM64 image's synthetic suite passed in an isolated container:
  PAT acquisition, package readiness, guest integration/clock, image
  validation, ARM installer/runtime, x86 installer regression, platform
  accelerator policy, and ARM research smoke. `tests/proprietary-artifacts.py`
  also passed on the host. These are synthetic checks, not new DSM acceptance.
- A separate clean patch check passed in an ARM64 container while forcing the
  GitHub source mirror; the source commit was verified before sequential
  application of patches 0001–0004. The host's direct GitLab/GitHub DNS path
  was unavailable. A production ARM64 build did complete using the Colima
  builder's reachable source path.

### amd64 and multi-platform status

- No native amd64 builder is configured. The available Buildx node runs on
  ARM64 and advertises amd64 through emulation, so an emulated build would not
  establish native amd64 runtime acceptance.
- The clean `linux/amd64` build did not complete: BuildKit could not resolve
  `docker/dockerfile:1` from Docker Hub because the registry TLS handshake
  timed out. An earlier attempt reached a later stage but failed with the ARM
  QEMU output missing; that execution was not accepted as a valid build. The
  amd64 image architecture and runtime remain unverified here. The hermetic
  default x86 command regression described below passes independently of the
  amd64 image.
- No multi-platform OCI index was assembled or inspected. No manifest or
  registry publication is claimed.
- The former container-based x86 command test entered the installer because
  its URL did not match the synthetic `dsm.ver` base. It was stopped before
  QEMU launch and its disposable container/storage were removed. The Phase 4A
  DSM container remained healthy and untouched. The replacement hermetic test
  below passed and contains no PAT URL or container execution.

### Hermetic x86 command regression — 2026-10-17

- Replaced the container-starting test with `tests/production-x86-command.py`,
  called by the existing shell entry point. It initializes the real default
  platform selection, obtains the accepted x86 argv from the existing
  `tests/fixtures/x86-baseline.sh`, and checks it against
  `tests/fixtures/virtualdsm.args` before invoking a PATH-injected fake
  `qemu-system-x86_64`.
- The test has no Docker call, storage mount, PAT URL, installer source, or
  real QEMU path. `curl` and `wget` are replaced by fail-fast logging stubs.
  The fake QEMU records argv and exits 37; the Python runner enforces a hard
  30-second timeout. This hermetic test passed and matched the exact accepted
  x86 argv, including default `virtualdsm`, amd64 guest, q35, and legacy boot.
- Existing x86 fixture/shell script checksum coverage remains in
  `tests/platform.sh`, which passed under Bash 5. The initial Bash 3.2 invocation
  on macOS failed on `${var^^}`; rerunning with Homebrew Bash 5 passed.

### Environment and remaining gates

- The existing Colima profile was verified as ARM64 VZ, 4 vCPU, 8 GiB RAM,
  100 GiB configured disk, nested virtualization enabled. It became reachable
  again without deleting its runtime disk. The existing Phase 4A DSM container
  remained healthy. An unprivileged `limactl list` did not enumerate Colima's
  managed instance, while Colima and Docker status confirmed the live VM.
- `/opt/homebrew/bin/bash` ShellCheck over the requested shell globs passed;
  `PATH=/opt/homebrew/bin:$PATH bash research/arm64/tests/smoke.sh` passed;
  `bash tests/platform.sh`, the hermetic x86 command regression,
  governance-docs and proprietary-artifact checks passed; `git diff --check`
  passed. The final ARM64 image architecture/ELF/dependency check passed.
  Ruby Psych parsed the changed workflow YAML. The repository config checker
  remains unrun: host interpreters lack PyYAML and an isolated `pip install
  PyYAML` attempt failed because `pypi.org` DNS was unavailable. The direct
  `tests/qemu-patches.sh` attempt also stopped before patching because both
  GitLab and GitHub DNS failed; the earlier forced GitHub mirror clean-apply
  passed in an ARM64 container. GitHub-hosted CI was not run.
- Local host is `arm64`; Buildx has one Colima ARM64 node advertising
  `linux/amd64` through emulation and no native amd64 node. A native amd64 host
  is required to satisfy the amd64 half of R1.
- R-level definitions: R0 is the Phase 4A baseline before integration work;
  R1 requires validated native production images on both amd64 and arm64;
  R2 adds the multi-platform OCI build/manifest and synthetic CI matrix; R3
  adds accelerator/lifecycle/runtime safety; R4 adds documentation, risk and
  x86 regression completion; R5 is the release candidate within declared
  boundaries. Keep the status wording `pre-R1` until both native architecture
  images pass. This project definition does not require an OCI manifest at R1.
- Current status is **Phase 4B: pre-R1**. The hermetic x86 command regression
  now passes, but no native amd64 builder is available and its production image
  remains unvalidated. The clean ARM64 build remains valid because no
  production code changed since it. OCI manifest validation and hosted CI are
  not complete; do not promote the phase.
