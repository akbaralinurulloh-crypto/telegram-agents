# TG Hunter

Manba Telegram kanallarni kuzatadi, postlarni AI bilan baholaydi, tozalaydi (telefon → **88 832 77 00**, reklama olib tashlanadi),
mos kelganlarini sizning kanalingizga joylaydi va kuniga 3 marta (08:00, 13:00, 20:00 Toshkent vaqti) hisobot yuboradi.

## Qoidalar (kodda majburiy)
- **Q1** Faqat manba kontent. Izoh faqat manba mazmuniga tayanadi: kod tekshiruvi (raqamlar manbada bormi) + ikkinchi AI tekshiruvi. Noaniq javob = post bekor.
- **Q2** Izohda hadis/rivoyat/diniy iqtibos yo'q (kalit so'zlar `config.yaml` da + AI tekshiruvi). 2 urinishdan keyin ham chiqsa — post bekor.
- **Q3** Faqat [asl kontent] + [qisqa izoh]. Hashtag, imzo, "obuna bo'ling" va h.k. qo'shilmaydi.
- **Q4** Reklama/telefon matnda, rasmda, videoda tozalanadi. **Ishonchli yopib bo'lmasa — joylanmaydi**, hisobotda "qo'lda ko'rib chiqing".

## Oqim
`xabar → dublikat → matn tozalash → media yuklash → baholash (≥ min_score) → rasm/video tozalash → izoh (faqat media bor postlarga) → joylash`.
Matn-only postlar o'zgartirilgan (tozalangan) holda izohsiz joylanadi. Media postlarda sarlavha = tozalangan asl matn + qisqa izoh
(1024 belgiga sig'masa: sarlavha = izoh, asl matn alohida xabar).

## O'rnatish (tavsiya: Docker)
1. `cp .env.example .env` va to'ldiring (API ID/HASH, BOT_TOKEN, ADMIN_ID, GEMINI_API_KEY yoki ANTHROPIC_API_KEY). Kanallar tayyor yozilgan.
2. `config.yaml` da `channel_topic` ni tekshiring/tahrirlang (baholash shunga tayanadi).
3. Telethon akkaunti **manba kanallarga a'zo** bo'lsin; bot **sizning kanalingizda admin** bo'lsin (faqat "Xabar yuborish").
4. Botga Telegramda `/start` yozing (aks holda u sizga yoza olmaydi).
5. Session olish (bir marta, telefon va kod so'raydi):
   `docker compose run --rm hunter python -m scripts.login`
6. Tekshiruv: `docker compose run --rm hunter python -m scripts.check --online`
7. Ishga tushirish: `docker compose up -d --build`. Loglar: `docker compose logs -f`.

### Docker'siz (Linux/macOS/WSL)
```
sudo apt install ffmpeg tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus tesseract-ocr-uzb
pip install -r requirements.txt
python -m scripts.login && python -m scripts.check --online && python -m app.main
```
Windows'da to'g'ridan-to'g'ri ishlatish uchun ffmpeg va Tesseract (rus, uzb tillari bilan) PATH ga qo'shilishi kerak; Docker yoki WSL osonroq.

## Birinchi ishga tushirish: DRY-RUN
`DRY_RUN=true` — hech narsa kanalga joylanmaydi; har bir "joylanadigan" post sizga botda ko'rsatiladi (🧪). 
Natijalar yoqsa: botga `/dryrun off` yozing — jonli rejim. Qaytarish: `/dryrun on`.

## Admin buyruqlari (faqat ADMIN_ID)
`/status` · `/pause` · `/resume` · `/dryrun on|off` · `/sources` · `/last 10`

## Xavfsizlik va ishonchlilik
- Kalitlar faqat `.env` da (gitga tushmaydi). Telethon session — `data/` (gitga tushmaydi).
- **Kill switch**: ketma-ket `kill_switch.max_consecutive_errors` ta xato → avtomatik pauza + sizga xabar.
- LLM vaqtincha ishlamasa (kvota/503): post yo'qolmaydi, 2, 4, 8… daqiqadan keyin qayta uriniladi; so'ng xato.
- FloodWait hurmat qilinadi; tarmoq uzilsa Telethon/aiogram qayta ulanadi.
- Manba post tahrirlansa/o'chirilsa: yozuv yangilanadi; allaqachon joylangan bo'lsa — sizga ogohlantirish.
- Har qaror DB (`audit_log`) da saqlanadi. Vaqtinchalik media har postdan keyin o'chiriladi.
- Hisobot yuborilmasa (bot xatosi) — har 10 daqiqada "⏰ Kechikkan hisobot" belgisi bilan qayta uriniladi.

## Cheklovlar (halol)
- Ovozdagi (audio) telefon raqamlar tekshirilmaydi; faqat ko'rinadigan yozuvlar.
- OCR mukammal emas (juda mayda/buzilgan yozuv o'tib ketishi mumkin) — shuning uchun DRY-RUN'da dastlabki natijalarni ko'zdan kechiring.
- Videodagi logotip aniqlansa qoplanmaydi, post "qo'lda ko'rib chiqing" ga tushadi. Rasmdagi logotip vizual AI orqali qoplanadi.
- Bot API 50 MB dan katta videoni yubora olmaydi (`media.max_video_mb: 45`).
- Gemini bepul tarifida kvota tez tugashi mumkin (post kechikadi, yo'qolmaydi). Pullik tarif yoki `llm.provider: anthropic`.

## Sinash
`pytest` (~4 daqiqa; OCR va video testlari ham bor). Jonli AI tuzoqlari: `python -m scripts.smoke_llm`.

## Holat
Stage 1–7 bajarilgan. Jonli (haqiqiy Telegram va AI bilan) tekshiruv foydalanuvchi muhitida DRY-RUN'da o'tkaziladi.
