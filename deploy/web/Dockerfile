# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.13.15-slim-bookworm@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1
ARG POWER_VERSION=3.7.10
ARG POWER_WHEEL_FILE=
ARG POWER_SOURCE_REVISION=unknown
ARG POWER_RELEASE_TAG=unknown
ARG SOURCE_DATE_EPOCH=0
ARG OCI_CREATED=unknown

FROM ${PYTHON_IMAGE} AS builder

ARG POWER_VERSION
ARG POWER_WHEEL_FILE
WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY skills/ ./skills/
COPY LICENSES/ ./LICENSES/
COPY THIRD_PARTY_NOTICES.md ./
COPY release/ ./release/

RUN set -eux; \
    if [ -n "${POWER_WHEEL_FILE}" ]; then \
      test -f "release/${POWER_WHEEL_FILE}"; \
      mkdir -p /dist; \
      cp "release/${POWER_WHEEL_FILE}" "/dist/${POWER_WHEEL_FILE}"; \
    else \
      python -m pip install --upgrade pip build; \
      python -m build --wheel --outdir /dist; \
    fi \
    && test -f "/dist/power_framework-${POWER_VERSION}-py3-none-any.whl"

FROM ${PYTHON_IMAGE} AS runtime

ARG POWER_VERSION
ARG POWER_SOURCE_REVISION
ARG POWER_RELEASE_TAG
ARG SOURCE_DATE_EPOCH
ARG OCI_CREATED
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --gid 10001 --system power \
    && useradd --uid 10001 --gid 10001 --system --home-dir /app --no-create-home --shell /usr/sbin/nologin power \
    && mkdir -p /app /brain /var/cache/power \
    && chown 10001:10001 /app /brain /var/cache/power

WORKDIR /app
COPY --from=builder "/dist/power_framework-${POWER_VERSION}-py3-none-any.whl" "/tmp/power_framework-${POWER_VERSION}-py3-none-any.whl"
COPY --from=builder /build/release/web-runtime.constraints.txt /tmp/web-runtime.constraints.txt
RUN python -m pip install \
        --constraint /tmp/web-runtime.constraints.txt \
        "/tmp/power_framework-${POWER_VERSION}-py3-none-any.whl[web,semantic,rerank]" \
    && rm "/tmp/power_framework-${POWER_VERSION}-py3-none-any.whl"

LABEL org.opencontainers.image.title="P.O.W.E.R Web UI" \
      org.opencontainers.image.description="Web UI for the unified POWER framework" \
      org.opencontainers.image.version="${POWER_VERSION}" \
      org.opencontainers.image.revision="${POWER_SOURCE_REVISION}" \
      org.opencontainers.image.ref.name="${POWER_RELEASE_TAG}" \
      org.opencontainers.image.created="${OCI_CREATED}" \
      org.opencontainers.image.created.epoch="${SOURCE_DATE_EPOCH}" \
      org.opencontainers.image.source="https://github.com/weby-homelab/power-framework"

USER 10001:10001
ENV POWER_WEB_HOST=0.0.0.0 \
    POWER_WEB_PORT=8080 \
    POWER_WEB_VAULT_PATH=/brain \
    POWER_WEB_AUTH_ENABLED=true \
    POWER_WEB_COOKIE_SECURE=true \
    XDG_CACHE_HOME=/var/cache/power

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)" || exit 1

ENTRYPOINT ["power-web"]
