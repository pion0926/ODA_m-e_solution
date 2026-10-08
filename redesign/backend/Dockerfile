FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app PLAYWRIGHT_BROWSERS_PATH=/opt/playwright HOME=/tmp
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends antiword file fonts-nanum libreoffice-impress poppler-utils tesseract-ocr tesseract-ocr-eng tesseract-ocr-kor \
    && rm -rf /var/lib/apt/lists/*

COPY redesign/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip==26.2.1 && pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
RUN python -m playwright install --with-deps chromium

COPY redesign/backend/kodame_intake ./kodame_intake
COPY backend/report_prompts.py ./report_prompts.py
COPY backend/report_few_shot.py ./report_few_shot.py
COPY backend/report_outline.py ./report_outline.py
COPY backend/report_writing_policy.py ./report_writing_policy.py
COPY backend/evaluation_specs.py ./evaluation_specs.py
COPY backend/oda_me ./backend/oda_me
COPY config/report_quality_profile.json ./config/report_quality_profile.json
COPY config/report_section_preview.json ./config/report_section_preview.json
COPY config/dac_scoring_checks.json ./config/dac_scoring_checks.json
COPY config/dac_evidence_rubric.json ./config/dac_evidence_rubric.json
COPY config/presentation_reference_profile.json ./config/presentation_reference_profile.json
COPY prompts ./prompts
COPY hwpx_sections ./hwpx_sections
COPY samples ./samples
COPY assets/rhwp ./rhwp

# Fail the image build, not the running service, if editable policy files are omitted.
RUN python -c "from kodame_intake.performance_risk_policy import RISK_SYSTEM_PROMPT; from kodame_intake.dac_scoring import RUBRIC_VERSION; assert RISK_SYSTEM_PROMPT and RUBRIC_VERSION"

EXPOSE 8100
RUN groupadd --gid 10001 kodame && useradd --uid 10001 --gid 10001 --no-create-home kodame && mkdir -p /app/data && chown 10001:10001 /app/data
USER 10001:10001
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/healthz', timeout=3)" || exit 1
CMD ["uvicorn", "kodame_intake.main:app", "--host", "0.0.0.0", "--port", "8100"]
