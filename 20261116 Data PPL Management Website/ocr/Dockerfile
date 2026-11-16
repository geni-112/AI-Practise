FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pil tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim \
 && rm -rf /var/lib/apt/lists/*
ENV OMP_THREAD_LIMIT=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/ocr
COPY service.py .
USER 65534:65534
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8091/health', timeout=3).close()"
CMD ["python3", "service.py"]
