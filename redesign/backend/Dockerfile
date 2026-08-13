FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8100 DATA_DIR=/app/data
WORKDIR /app
COPY redesign/backend/app.py ./app.py
RUN mkdir -p /app/data
EXPOSE 8100
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/healthz', timeout=3)" || exit 1
CMD ["python", "app.py"]
