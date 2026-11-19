FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/app/data FASTEMBED_MODEL_PATH=/opt/embedding-model
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-fas libgomp1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY scripts/fetch_model.py /tmp/fetch_model.py
RUN python /tmp/fetch_model.py "$FASTEMBED_MODEL_PATH"
RUN useradd --create-home --uid 10001 app && mkdir /app/data /app/staticfiles \
    && chown app:app /app/data /app/staticfiles
COPY --chown=app:app . .
RUN chmod +x /app/start.sh
USER app
RUN DJANGO_SECRET_KEY=build-static-only python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["sh", "/app/start.sh"]
