FROM python:3.13-slim AS builder

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir build && python -m build --wheel

FROM python:3.13-slim

RUN groupadd -r power && useradd -r -g power -d /app -s /sbin/nologin power

WORKDIR /app
COPY --from=builder /app/dist/*.whl .
RUN pip install --no-cache-dir *.whl && rm *.whl

USER power
ENV POWER_VAULT_DIR=/vault

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["python", "-m", "power_framework.mcp"]
