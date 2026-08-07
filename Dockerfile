FROM python:3.12-slim-bookworm

ARG RHWP_VERSION=0.7.10
ARG RHWP_ARCHIVE=rhwp-v${RHWP_VERSION}-linux-x86_64.tar.gz

LABEL org.opencontainers.image.title="ODA ImpactOps AI" \
      org.opencontainers.image.description="ODA monitoring, evaluation, evidence and report management application" \
      org.opencontainers.image.version="1.0.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    HOST=0.0.0.0 \
    PORT=8001 \
    DATA_DIR=/app/data \
    MAX_REQUEST_BYTES=134217728 \
    RHWP_BIN=/usr/local/bin/rhwp

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tar tini \
    && curl -fsSL "https://github.com/edwardkim/rhwp/releases/download/v${RHWP_VERSION}/${RHWP_ARCHIVE}" -o /tmp/rhwp.tar.gz \
    && tar -xzf /tmp/rhwp.tar.gz -C /tmp \
    && find /tmp -type f -name rhwp -exec install -m 0755 {} /usr/local/bin/rhwp \; \
    && rm -rf /var/lib/apt/lists/* /tmp/rhwp.tar.gz /tmp/rhwp-v${RHWP_VERSION}-linux-x86_64

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY . .

RUN mkdir -p /app/data/uploads /app/data/extracted_text /app/data/evaluations /app/data/reports

EXPOSE 8001
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/healthz', timeout=3)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "backend/app.py"]
