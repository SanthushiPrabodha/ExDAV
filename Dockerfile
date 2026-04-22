# Universal backend container for Ex-DAV.
# Works on Railway, Fly.io, Render (Docker runtime), Google Cloud Run, etc.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TESSERACT_CMD=/usr/bin/tesseract

# System deps: tesseract for OCR, libgl/libglib for OpenCV (headless wheel
# still benefits from having libglib available for some codecs).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libglib2.0-0 \
        libsm6 \
        libxrender1 \
        libxext6 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-deploy.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements-deploy.txt

COPY backend ./backend
COPY src ./src

RUN mkdir -p backend/uploads

EXPOSE 8000

# $PORT is supplied by Railway / Fly / Render at runtime; default to 8000 locally.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
