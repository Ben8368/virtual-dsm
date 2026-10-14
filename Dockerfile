# syntax=docker/dockerfile:1

FROM qemux/qemu:7.50 AS base

# BuildKit uses TARGETPLATFORM for every stage, independently of guest CPU.
FROM debian:trixie-slim AS arm-qemu-build
ARG TARGETARCH
ARG QEMU_VERSION="8.2.2"
RUN apt-get update && apt-get --no-install-recommends -y install \
    build-essential ca-certificates git meson ninja-build pkg-config \
    python3-venv libglib2.0-dev libpixman-1-dev libslirp-dev \
    && rm -rf /var/lib/apt/lists/*
COPY patches/qemu/8.2.2/ /patches/
COPY --chmod=755 scripts/build-arm-qemu.sh /build-arm-qemu.sh
COPY --chmod=755 scripts/apply-qemu-patches.sh /apply-qemu-patches.sh
RUN /build-arm-qemu.sh

FROM base AS runtime
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=arm-qemu-build /out/qemu-system-aarch64 /usr/local/bin/qemu-system-aarch64

ARG VERSION_ARG="0.0"
ARG VERSION_CSTRUCT="4.7"

ARG DEBCONF_NOWARNINGS="yes"
ARG DEBIAN_FRONTEND="noninteractive"
ARG DEBCONF_NONINTERACTIVE_SEEN="true"

RUN <<EOF
  set -eu

  apt-get update
  apt-get --no-install-recommends -y install \
    fakeroot \
    xz-utils \
    tar \
    e2fsprogs \
    util-linux \
    python3-msgpack \
    python3-pysodium \
    openssh-client \
    libslirp0 \
    libpixman-1-0

  apt-get clean

  # Install Python dependencies
  pip3 install --no-cache-dir --break-system-packages --root-user-action=ignore "dissect.cstruct==$VERSION_CSTRUCT" "dissect.extfs==3.15"

  qemu-system-aarch64 --version
  qemu-system-x86_64 --version
  if ldd /usr/local/bin/qemu-system-aarch64 | grep -q "not found"; then exit 1; fi

  # Set version file
  echo "$VERSION_ARG" > /etc/version

  rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
EOF

COPY --chmod=755 ./src /run/
COPY --chmod=755 ./scripts/package-readiness.py /run/package-readiness.py
COPY --chmod=755 ./web /var/www/
COPY --chmod=744 ./web/conf/nginx.conf /etc/nginx/default.conf
COPY --chmod=755 --from=qemux/qemu-host:2.06 /qemu-host.bin /run/host.bin
ADD --chmod=775 https://raw.githubusercontent.com/sud0woodo/patology/refs/heads/main/patology.py /run/extract.py

VOLUME /storage
EXPOSE 445 5000

ENV RAM_SIZE="2G"
ENV CPU_CORES="2"
ENV DISK_SIZE="256G"

HEALTHCHECK --interval=60s --start-period=45s --retries=2 CMD ["/run/check.sh"]

ENTRYPOINT ["/usr/bin/tini", "-s", "/run/entry.sh"]
