# API MEDISIGHT avec Tesseract OCR (français, arabe, anglais) : aucune installation Windows ni droits administrateur.
FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra tesseract-ocr-ara tesseract-ocr-eng \
      libglib2.0-0 fonts-dejavu-core fonts-noto-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt backend/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY backend/ ./
COPY data/ /app/data/
ENV PYTHONUNBUFFERED=1 TESSERACT_LANGS=fra+ara+eng DATA_DIR=/app/data
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
