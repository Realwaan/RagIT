FROM node:22-bookworm-slim@sha256:4b150b48b4116e2a22f2c39cc27025fbf4f153e2078fd3b14d159fdb5c7279da AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY frontend/ frontend/
ARG VITE_CLERK_PUBLISHABLE_KEY
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY
RUN test -n "$VITE_CLERK_PUBLISHABLE_KEY" && npm run build

FROM python:3.13-slim-bookworm@sha256:281d39ff02e3b389401586134ff9e6572954687822a58055ec07a60ded4e0b7f AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    RAGIT_DATA_DIR=/var/lib/ragit/data \
    RAGIT_PREVIEWS_DIR=/var/lib/ragit/previews \
    RAGIT_CROPS_DIR=/var/lib/ragit/crops \
    FASTEMBED_CACHE_PATH=/opt/ragit-models/fastembed
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt constraints-runtime.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints-runtime.txt && pip check
# Download local inference weights at build time, before accepting uploads.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='sentence-transformers/all-MiniLM-L6-v2'); from rapidocr import RapidOCR; import numpy as np; ocr = RapidOCR(); sample = np.full((32, 128, 3), 255, dtype=np.uint8); ocr(sample, use_det=False, use_cls=True, use_rec=True); ocr(sample, use_det=True); assert all(model is not None for model in (ocr.text_det, ocr.text_cls, ocr.text_rec))"
COPY app/ app/
COPY --from=frontend /build/app/static/assistant/ app/static/assistant/
RUN useradd --uid 10001 --create-home ragit \
    && mkdir -p /var/lib/ragit/data /var/lib/ragit/previews /var/lib/ragit/crops \
    && chown -R ragit:ragit /var/lib/ragit /opt/ragit-models
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "120"]

