# TG Hunter

Telegram kontent kuzatuvchi va joylovchi AI agent. Loyiha bosqichma-bosqich quriladi.

## Holat
- [x] **Stage 1** — struktura, config, DB (SQLAlchemy + Alembic), Telethon watcher (faqat o'qish)
- [x] **Stage 2** — dedupe (matn hash + pHash), matn tozalash (telefon → 88 832 77 00, reklama)
- [x] **Stage 3** — LLM qatlami (Gemini | Claude), scorer, captioner, validatorlar
- [x] **Stage 4** — media tozalash (rasm/video OCR, 88 832 77 00, logotip tekshiruvi)
- [ ] Stage 5 — publisher (dry-run) + admin buyruqlari
- [ ] Stage 6 — hisobotlar + scheduler
- [ ] Stage 7 — Docker, to'liq README

## Tizim talablari
- `ffmpeg` va `tesseract-ocr` (+ `tesseract-ocr-rus`, `tesseract-ocr-uzb`, `tesseract-ocr-eng`):
  `sudo apt install ffmpeg tesseract-ocr tesseract-ocr-rus tesseract-ocr-uzb tesseract-ocr-eng`
- OCR ikki dvigatel bilan ishlaydi (Tesseract + RapidOCR); biri o'tkazib yuborganini ikkinchisi ushlaydi.

## Ishga tushirish (Stage 1)
```bash
cd tg_hunter
pip install -r requirements.txt
cp .env.example .env        # to'ldiring
python -m scripts.login     # bir marta: telefon + kod
python -m app.main          # manba kanallarni o'qiydi, DB va logga yozadi
pytest
```
Stage 1 hech narsa joylamaydi va hech kimga yubormaydi.
