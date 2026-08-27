# 🤖 Autonomous Telegram AI Media Creator & Intelligence Platform (Enterprise v2.0)

> **"Eng sara kontentni mustaqil topadigan, tahlil qiladigan, saralaydigan, yaratadigan, joylashtiradigan va natijadan o'rganadigan Avtonom AI Media Kreator"**

---

## 🏛 Tizim Arxitekturasi

```text
Telegram Sources (1..N)
        ↓
Source Manager & Registry
        ↓
Resilient Media Collector
        ↓
Media Storage Layer (Local / S3 / R2)
        ↓
Technical Quality Engine (FFprobe/PIL) + Perceptual Duplicate Engine (SHA256, pHash)
        ↓
Multi-Dimensional Gemini Vision Analyzer (Emotional, Relevance, Uniqueness, Quality)
        ↓
Content Scoring Engine (Multi-factor Weights)
        ↓
Audience Intelligence + Category Fatigue Engine + Diversity Balancer
        ↓
Content Curator (Candidate Pool Selection & AI Decision Explainer)
        ↓
Media Creator Studio (FFmpeg) + 3-Style Caption AI Engine
        ↓
Smart Scheduler (Posting Window & Heatmap)
        ↓
Human-in-the-Loop Governance Gate (MANUAL / SEMI_AUTO / AUTO)
        ↓
Idempotent Telegram Publisher
        ↓
Post Analytics Scraper (Views, Reactions, Forwards, Engagement Rate)
        ↓
Learning Engine & AI Strategist (Daily Insights & Adaptive Weights)
        ↓
FastAPI Backend + Web Control Center Dashboard
```

---

## 🌟 Yangi Imkoniyatlar

1. **Ko'p o'lchovli AI Tahlil**: Rasm va videolarni 6 xil mezon (Visual, Emotional, Relevance, Uniqueness, Freshness, Information) bo'yicha 0-100 shkalada tahlil qiladi.
2. **Texnik Sifat va Dublikat Nazorati**: Piksellar soni, yorug'lik, kontrast va `pHash`/`dHash` orqali qayta ishlangan/qirqilgan dublikatlarni ham 100% aniqlaydi.
3. **Kategoriya Toliqishi (Fatigue) va Xilma-xillik (Diversity)**: Ketma-ket bir xil mavzu chiqishining oldini oladi va kanal auditoriyasini zeriktirmaydi.
4. **Nomzodlar Hovuzi (Candidate Pool) va Kurator**: Eng yaxshi postlarni jamlab, ulardan eng mos kelganini saralaydi.
5. **AI Strategist va Learning Engine**: Postlarning ko'rishlar soni va reaksiyalarini tahlil qilib, kunlik xulosalar va tavsiyalar beradi.
6. **Web Control Center Dashboard**: Barcha jarayonlarni real vaqtda kuzatish va boshqarish uchun zamonaviy Dark-mode veb-interfeysi.
7. **Admin Telegram Bot**: Telegram orqali `/status`, `/today`, `/sources`, `/strategist` buyruqlari va interaktiv tugmalar.

---

## 💻 Ishga Tushirish

### 1. Bog'liqliklarni o'rnatish
```bash
pip install -r requirements.txt
```

### 2. Testlarni ishga tushirish
```bash
python -m pytest tests/
```

### 3. Agent va Dashboardni ishga tushirish
```bash
python agent.py
```

Dashboard brauzerda ochiladi: **`http://localhost:10000/dashboard`** (yoki `http://localhost:10000/`)

---

## 🌐 24/7 Cloud Deployment (Render.com / Docker)

- **Render.com**: `render.yaml` orqali avtomatik 1-bosishda deploy qilinadi.
- **Docker Compose**:
  ```bash
  docker compose up -d --build
  ```

---

## 📊 Admin Telegram Bot Buyruqlari
- `/start` — Boshqaruv markaziga xush kelibsiz
- `/status` — Tizim salomatligi va navbatlar holati
- `/today` — Bugungi yig'ilgan, joylangan va saralangan kontentlar
- `/sources` — Manba kanallar va ularning ishonch ko'rsatkichlari
- `/strategist` — AI Strategist kundalik tavsiyalari
