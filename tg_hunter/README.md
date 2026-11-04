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

### Serverda (24/7, tavsiya)
Ubuntu 22.04/24.04, kamida 2 vCPU / 4 GB RAM. Serverda root sifatida:
```
curl -fsSL https://raw.githubusercontent.com/akbaralinurulloh-crypto/telegram-agents/main/tg_hunter/deploy/setup.sh -o setup.sh   # private repo: skriptni qo'lda nusxalang
bash setup.sh      # Docker, swap, devor, GitHub deploy kaliti; kalit so'ralsa — GitHub'ga qo'shib, qayta ishga tushiring
```
Keyin skript chiqargan 6 qadamni bajaring. Yangilash: `bash deploy/update.sh`.
Avtomatik deploy (ixtiyoriy): `.github/workflows/deploy.yml` — repo Variables'da `DEPLOY_ENABLED=true` va Secrets: `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`.

### GitHub orqali ulash (Railway): tugmalar bilan
Server o'rnatmaysiz: GitHub reponi ulaysiz, Railway o'zi quradi va 24/7 ishga tushiradi. Narxi ishlatilganiga qarab (taxminan $5-10/oy).
Bepul rejalar (masalan Render Free: 0.1 CPU, 512 MB, 15 daqiqada uxlaydi, disk o'chadi) OCR va video uchun yetmaydi.

1. **O'zgaruvchilarni tayyorlang** (noutbukda, bir marta; Docker kerak): `RAILWAY_UCHUN_SESSIYA.bat` ni ikki marta bosing.
   U agentni to'xtatadi, Telegramga qayta kiritadi (telefon + kod) va Railway uchun hamma o'zgaruvchilarni (kalitlar + sessiya matni)
   toza qatorlar qilib clipboardga nusxalaydi. Qo'lda: `python -m scripts.login`, keyin `python -m scripts.export_session --railway`.
   (`.env` ni xom nusxalamang: Railway `DRY_RUN=true  # izoh` dagi izohni ham qiymatga qo'shib yuboradi.)
2. railway.com -> **Login with GitHub** -> **New Project -> Deploy from GitHub repo** -> `telegram-agents`.
3. Xizmat **Settings**: **Root Directory** = `/tg_hunter`; **Branch** = `main` (PR qo'shilgach) yoki `claude/lucid-curie-94o0u2`.
   Dockerfile topilmasa, **Variables** ga `RAILWAY_DOCKERFILE_PATH=Dockerfile` qo'shing.
4. **Variables -> Raw Editor**: clipboarddagi matnni bitta Ctrl+V bilan qo'ying (TG_API_ID, TG_API_HASH, BOT_TOKEN, ADMIN_ID,
   TARGET_CHANNEL, SOURCE_CHANNELS, GEMINI_API_KEY, DRY_RUN=true, TG_SESSION_STRING) va **Update Variables**. (`TG_SESSION_PATH`, `DATABASE_URL` shart emas.)
5. **Volumes -> New Volume**, Mount path: `/app/data`. **MAJBURIY**: baza va sessiya fayli shu yerda saqlanadi; usiz har qayta ishga tushganda tarix yo'qoladi.
6. **Deploy**. Loglarda "TG Hunter ishga tushdi" chiqadi, bot sizga yozadi; `/status`.

Yangilash: GitHub'ga o'zgarish tushsa, Railway o'zi qayta quradi; `config.yaml` ham GitHub'da tahrirlanadi.
**Xavfsizlik:** `TG_SESSION_STRING` akkauntga to'liq kirish beradi: faqat Railway Variables'da tursin, GitHub'ga yozmang.
Railway va GitHub'da 2 bosqichli tasdiqlashni yoqing, reponi private qiling.

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
`/status` · `/report` (bugungi hisobot darrov) · `/pause` · `/resume` · `/dryrun on|off` · `/sources` (kanal/guruh turi bilan) · `/last 10`

## Kompyuter uxlasa (laptop) nima bo'ladi
Docker Desktop (WSL2) da kompyuter uyquga ketganda agent ham to'xtaydi. Uyg'ongach agent: (1) `💤 ... to'xtab turgan edi` xabarini yuboradi,
(2) o'tkazib yuborilgan hisobotlarni (12 soatgacha) `⏰ Kechikkan` belgisi bilan yuboradi, (3) Telegram yangiliklarini qayta oladi va
manbalarni o'zi tekshiradi. Zaxira tekshiruv har 10 daqiqada ishlaydi (Telegram yangilik yubormasa ham post o'tib ketmaydi).
Uzluksiz 24/7 uchun baribir VPS kerak; laptopda: `powercfg /change standby-timeout-ac 0` (quvvatga ulangan paytda uyquni o'chiradi).

## Manba GURUH bo'lsa
Manba sifatida kanal o'rniga **guruh** (a'zolar yozishadigan chat) ko'rsatilsa, agent uni sukut bo'yicha **o'tkazib yuboradi**
(a'zolarning yozishmalarini qayta ishlamaslik va keraksiz shovqin/LLM sarfini oldini olish uchun). Ishga tushganda bot ogohlantiradi,
`/sources` har manbaning turini ko'rsatadi. Guruh kerak bo'lsa: `config.yaml` da `watcher: include_groups: true`.

## Yangilash (Windows)
Yangi `tg_hunter_yangilanish*.zip` ni Downloads'ga yuklab oling va `YANGILASH.bat` ni ikki marta bosing: u eng yangi zipni topadi,
fayllarni almashtiradi (`.env`, `config.yaml`, `data` tegilmaydi) va `docker compose up -d --build` ni bajaradi.

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
