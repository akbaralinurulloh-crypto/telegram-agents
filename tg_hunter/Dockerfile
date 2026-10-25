FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus tesseract-ocr-uzb libgl1 libglib2.0-0 tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1 TZ=Asia/Tashkent
CMD ["python", "-m", "app.main"]
