FROM python:3.12-slim

ARG RHWP_VERSION=0.7.10
ARG RHWP_ARCHIVE=rhwp-v${RHWP_VERSION}-linux-x86_64.tar.gz

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8001 \
    RHWP_BIN=/usr/local/bin/rhwp

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tar \
    && curl -fsSL "https://github.com/edwardkim/rhwp/releases/download/v${RHWP_VERSION}/${RHWP_ARCHIVE}" -o /tmp/rhwp.tar.gz \
    && tar -xzf /tmp/rhwp.tar.gz -C /tmp \
    && find /tmp -type f -name rhwp -exec install -m 0755 {} /usr/local/bin/rhwp \; \
    && rm -rf /var/lib/apt/lists/* /tmp/rhwp.tar.gz /tmp/rhwp-v${RHWP_VERSION}-linux-x86_64

RUN pip install --no-cache-dir openpyxl python-pptx pypdf master-of-hwp

WORKDIR /app

COPY . .

EXPOSE 8001

CMD ["python", "backend/app.py"]
