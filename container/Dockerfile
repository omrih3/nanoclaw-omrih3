# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
# The BuildKit frontend above is pinned by digest, so a build fetches it by
# content address and never asks Docker Hub to resolve the `1.7` tag first. The
# tag lookup is the HEAD request that returned 500 and took two registry-skills
# legs down on 2026-09-07 with the code untouched. Resolved with
# `crane digest docker/dockerfile:1.7` (docker buildx imagetools inspect agrees).
# Bump the tag and digest together.
# NanoClaw Agent Container
# Runs Claude Agent SDK in isolated Linux VM with browser automation.
#
# Runtime split:
#   - agent-runner (our TypeScript code): Bun, mounted RO at /app/src by host
#   - globally-installed Node CLIs (claude-code, agent-browser): pnpm + Node
#
# Source is never baked in — /app/src is provided by a shared read-only
# bind mount at runtime (see src/container-runner.ts). Source-only changes
# never require an image rebuild.

# Pinned by digest so a rebuild cannot reuse a cached older base; bump tag and digest together.
FROM node:22.23.4-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d

# ---- Build-time arguments ----------------------------------------------------
# CJK fonts add ~200MB. Opt in only if you render Chinese/Japanese/Korean text.
ARG INSTALL_CJK_FONTS=false

# Pin versions for reproducibility. Bump deliberately — unpinned installs mean
# every rebuild silently picks up the latest and can break in lockstep across
# all users. The global Node CLIs (claude-code, agent-browser) are
# pinned in cli-tools.json so a skill can add one with a json-merge; Bun (the
# runtime) is pinned here because it installs from a different source.
ARG BUN_VERSION=1.4.4

# ---- System dependencies -----------------------------------------------------
# tini: correct PID 1 / signal forwarding so outbound.db writes finalize on
# SIGTERM instead of being orphaned by the shell entrypoint.
# poppler-utils: Claude Code's Read tool shells out to pdftoppm to open a PDF;
# without it every PDF a user sends comes back as an error.
# tesseract-ocr(+eng/heb/osd): local OCR for images and scanned PDFs (English + Hebrew).
# ffmpeg + python3(-venv): audio decoding and the faster-whisper venv (local speech-to-text).
# fonts-dejavu-core: has Hebrew glyphs, so Chromium renders Hebrew instead of empty boxes.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        fonts-dejavu-core \
        fonts-liberation \
        fonts-noto-color-emoji \
        libgbm1 \
        libnss3 \
        libnss3-tools \
        libatk-bridge2.0-0 \
        libgtk-3-0 \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libasound2 \
        libpangocairo-1.0-0 \
        libcups2 \
        libdrm2 \
        libxshmfence1 \
        ca-certificates \
        curl \
        ffmpeg \
        git \
        poppler-utils \
        python3 \
        python3-venv \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-heb \
        tesseract-ocr-osd \
        tini \
        unzip \
    && if [ "$INSTALL_CJK_FONTS" = "true" ]; then \
        apt-get install -y --no-install-recommends fonts-noto-cjk; \
       fi \
    && rm -rf /var/lib/apt/lists/*

# Chromium path for agent-browser / Playwright consumers
ENV AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/chromium
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium
# Belt-and-braces: prevent Playwright's postinstall from downloading its own
# ~300MB Chromium. We've already installed the system one above.
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# ---- Bun runtime -------------------------------------------------------------
# Install via the official script (handles multi-arch detection), then move
# the binary to /usr/local/bin so the non-root `node` user can execute it.
# The version check fails the build if the script installed anything but the pin.
RUN curl -fsSL https://bun.sh/install | bash -s "bun-v${BUN_VERSION}" && \
    install -m 0755 /root/.bun/bin/bun /usr/local/bin/bun && \
    rm -rf /root/.bun && \
    test "$(bun --version)" = "${BUN_VERSION}"

# ---- Local speech-to-text (faster-whisper) -----------------------------------
# Venv at /opt/whisper, model baked into /opt/whisper-models so every agent can
# transcribe offline with `whisper-transcribe <file>`. CPU + int8. Placed before
# the frequently bumped layers so the ~1.6GB model layer stays cached.
ARG FASTER_WHISPER_VERSION=1.2.1
ARG WHISPER_MODEL=large-v3-turbo
ENV WHISPER_MODEL_DIR=/opt/whisper-models
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m venv /opt/whisper \
    && /opt/whisper/bin/pip install "faster-whisper==${FASTER_WHISPER_VERSION}" \
    && /opt/whisper/bin/python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL}', device='cpu', compute_type='int8', download_root='/opt/whisper-models')" \
    && chmod -R a+rX /opt/whisper /opt/whisper-models
# Lighter models for speed on a weak CPU. Separate layer so the large model above stays cached.
ARG WHISPER_EXTRA_MODELS="small base tiny"
RUN for m in ${WHISPER_EXTRA_MODELS}; do \
      /opt/whisper/bin/python -c "from faster_whisper import WhisperModel; WhisperModel('$m', device='cpu', compute_type='int8', download_root='/opt/whisper-models')" || exit 1; \
    done \
    && chmod -R a+rX /opt/whisper-models
COPY whisper-transcribe.py /usr/local/bin/whisper-transcribe
RUN chmod 0755 /usr/local/bin/whisper-transcribe

# ---- Google Maps scraper (gosom/google-maps-scraper) -------------------------
# Static Go binary + its Playwright driver/Chromium, lifted from the published
# image (pinned by digest). Env is set by the gmaps-scrape wrapper only, so it
# does not leak into other Playwright consumers. Bump tag and digest together.
COPY --from=gosom/google-maps-scraper:v1.18.1@sha256:72cbe16b6832d35971611659807fa85bdab19715dd29f74db5ae01714ca18666 /usr/bin/google-maps-scraper /usr/local/bin/google-maps-scraper
COPY --from=gosom/google-maps-scraper:v1.18.1@sha256:72cbe16b6832d35971611659807fa85bdab19715dd29f74db5ae01714ca18666 /opt/browsers /opt/gmaps/browsers
COPY --from=gosom/google-maps-scraper:v1.18.1@sha256:72cbe16b6832d35971611659807fa85bdab19715dd29f74db5ae01714ca18666 /opt/ms-playwright-go /opt/gmaps/driver
COPY gmaps-scrape.sh /usr/local/bin/gmaps-scrape
# Browsers dir must be writable: playwright-go runs `install chromium` (a no-op, but it takes a lock there) on every start.
RUN chmod -R a+rX /opt/gmaps && chmod -R a+rwX /opt/gmaps/browsers && chmod 0755 /usr/local/bin/gmaps-scrape

# ---- agent-runner deps -------------------------------------------------------
# Deps are cached independently of CLI versions. Source is NOT baked in —
# it's provided by the shared RO mount at runtime.
WORKDIR /app

COPY agent-runner/package.json agent-runner/bun.lock ./

RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile

# ---- pnpm + global Node CLIs -------------------------------------------------
# Most stable first, most frequently bumped last. Bumping claude-code
# (the most common change) only invalidates one layer.
#
# only-built-dependencies gates pnpm's supply-chain policy:
#   - agent-browser has a postinstall build step.
#   - @anthropic-ai/claude-code's postinstall downloads the native Claude
#     binary (linux-arm64 variant on our image). Without the allowlist
#     the SDK fails at spawn time with "native binary not found".
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
# Pin pnpm to match the host (package.json packageManager). pnpm 11 stopped
# honoring `only-built-dependencies[]=` in .npmrc for global installs, which
# silently skips claude-code's native-binary postinstall and agent-browser's
# bin chmod — the agent then crashes at runtime with "native binary not
# installed". Keep this in lockstep with package.json's `packageManager`.
ARG PNPM_VERSION=10.34.5
RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION} --activate

# Global Node CLIs the agent invokes at runtime live in cli-tools.json so a
# skill can add one with a json-merge instead of editing this Dockerfile.
# install-cli-tools.sh installs each via pnpm (pinned), writing the per-tool
# only-built-dependencies opt-ins it reads from the manifest.
COPY cli-tools.json install-cli-tools.sh /tmp/
RUN --mount=type=cache,target=/root/.cache/pnpm \
    sh /tmp/install-cli-tools.sh /tmp/cli-tools.json

# ---- ncl CLI wrapper ----------------------------------------------------------
# Actual script lives in the mounted source at /app/src/cli/ncl.ts.
RUN printf '#!/bin/sh\nexec bun /app/src/cli/ncl.ts "$@"\n' > /usr/local/bin/ncl && \
    chmod +x /usr/local/bin/ncl

# ---- Entrypoint --------------------------------------------------------------
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# ---- Workspace + permissions -------------------------------------------------
RUN mkdir -p /workspace/group /workspace/extra && \
    chown -R node:node /workspace && \
    chmod 777 /home/node

# Drop setuid-root from the binaries Debian ships (mount, su, passwd, ...). The
# agent runs unprivileged and needs none of them.
RUN find / -xdev -perm -4000 -type f -exec chmod u-s {} + || true

USER node
WORKDIR /workspace/group

# Only applies to a bare `docker run` — the host spawn overrides ENTRYPOINT and
# passes --init instead (see hardeningArgs in src/container-runner.ts).
ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]

# ---- Provenance labels -------------------------------------------------------
# LAST on purpose. An ARG invalidates every layer below it, so declaring these
# up with the other build-args would make an otherwise-cached rebuild redo
# `bun install` and the pnpm global CLIs on every existing install, for two
# pieces of metadata. Labels have no filesystem effect, so they cost nothing here.
#
# Which lockfile the baked /app/node_modules came from: /app/src is mounted from
# the host checkout at every spawn, so an image and a checkout whose lockfiles
# disagree fail as a missing module inside a `--rm` container with no logs.
# container/pull.sh checks this before retagging. build.sh passes it; a bare
# `docker build` leaves it empty, which the pull path treats as unverifiable.
#
# image-source defaults to `local` so anything built from this file is honest
# unless its builder says otherwise — the retag cannot forge it after the fact.
ARG AGENT_RUNNER_LOCK_SHA256=
LABEL dev.nanoclaw.agent-runner-lock-sha256="${AGENT_RUNNER_LOCK_SHA256}"
ARG IMAGE_SOURCE=local
LABEL dev.nanoclaw.image-source="${IMAGE_SOURCE}"
