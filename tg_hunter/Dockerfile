FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus tesseract-ocr-uzb libgl1 libglib2.0-0 tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN mkdir -p /app/data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# cryptg: Telethon uchun ixtiyoriy tezlatgich. Faqat TAYYOR wheel bo'lsa o'rnatiladi (Rust kompilyatori kerak emas);
# bo'lmasa (masalan yangi versiyada wheel hali yuklanmagan) sof-Python AES ishlaydi: biroz sekinroq, lekin qurish to'xtamaydi.
RUN pip install --no-cache-dir --only-binary=:all: "cryptg>=0.4" || echo "cryptg o'rnatilmadi: sof-Python AES ishlatiladi"
COPY . .

ENV PYTHONUNBUFFERED=1 TZ=Asia/Tashkent
CMD ["python", "-m", "app.main"]
