# 🏛 TAMC (Telegram Autonomous Media Creator) — Repository Audit Report

**Date:** 2026-08-27  
**Auditor:** Lead Software Architect, Senior Backend & AI Systems Engineer  
**Document Status:** Complete (Phase 0 Audit)

---

## 1. Existing Architecture
The repository is structured as a modern Python 3.13 asynchronous application with clean separation between core configuration, collectors, AI engines, models, database layer, REST API, admin bot, and web dashboard.

```text
[Telegram Sources (4 Channels)] ──► [Telethon MTProto Collector]
                                              │
                                              ▼
                                    [Multi-Stage Ingestion]
                                              │
    ┌───────────────────────┬─────────────────┴────────────────┬────────────────────────┐
    ▼                       ▼                                  ▼                        ▼
[Quality Engine]    [Duplicate Engine]                [Target Auditor]         [Unified Queue]
 (Laplacian Blur)    (5-Frame pHash)                  (@muhtasham memory)     (Async Retry + DLQ)
    │                       │                                  │                        │
    └───────────────────────┼──────────────────────────────────┘                        │
                            ▼                                                           ▼
                [Gemini Vision 3.6 Flash] ◄─────────────────────────────────────────────┘
                            │
                            ▼
        [Content DNA & Scoring 2.0 (100-pt Weighted)]
                            │
                            ▼
           [Fatigue Engine & Diversity Sequencer]
                            │
                            ▼
            [Idempotent Publisher with Lock] ──► [@muhtashamtraveluzz (Live Channel)]
                            │
                            ├──────────────────────────────────┐
                            ▼                                  ▼
        [Reporting Bot (@Muhtashamagent_bot)]        [FastAPI Web Control Center]
         (08:00, 13:00, 21:00 Cron Reports)          (Power BI Style 8-Panel View)
                            │
                            ▼
             [Google Sheets Live Webhook]
```

---

## 2. Existing Services
1. **Collector Service (`app/collectors/telegram_collector.py`)**: Asynchronous MTProto listener for `@MuhtashamUmra`, `@Muhtasham_travel_Umra_sari`, `@muhtashamtravel`, and `@nurlisafar`.
2. **Unified Queue (`app/core/queue.py`)**: In-memory asynchronous queue manager with backoff retries (`[5, 15, 60, 300]`s) and Dead Letter Queue (`_dlq`).
3. **AI Vision & Captioner (`app/engines/ai_provider.py` & `captioner.py`)**: Google Gemini 3.6 Flash provider with fallback models (`3.5-flash`, `flash-latest`).
4. **Quality & Duplicate Guard (`app/engines/quality.py` & `duplicate.py`)**: Multi-point video keyframing (10%, 30%, 50%, 70%, 90%) + Laplacian edge variance sharpness analysis.
5. **Target Channel Auditor (`app/engines/target_auditor.py`)**: Continuous 10-minute deep scanner indexing `@muhtashamtraveluzz` historical fingerprints.
6. **Smart Publisher (`app/engines/publisher.py`)**: Serialized async lock (`_publish_lock`) publisher with live pre-publish Telegram channel similarity check.
7. **Reporting Engine & Scheduler (`app/engines/reporting_engine.py` & `report_scheduler.py`)**: Automated 08:00, 13:00, 21:00 `Asia/Tashkent` executive reporter.
8. **Admin Bot Polling (`app/bot/admin_bot.py`)**: Long-polling bot API dispatcher responding to `/report`, `/top`, `/sources`, `/health`, and inline buttons.
9. **FastAPI Web Service (`app/api/`)**: REST API and static dashboard serving on port 10000.

---

## 3. Existing Database Schema
Primary database: SQLAlchemy ORM on SQLite (`agent_database.sqlite`) / PostgreSQL compatible.

* `sources`: Tracked Telegram channels, priority, trust score (0.0–1.0), quality score.
* `source_messages`: Historical seen message IDs per source to prevent re-processing.
* `media_assets`: Stored local files, MIME types, SHA-256, perceptual hashes (`phash`, `dhash`).
* `media_analysis`: Category, visual tags, audio summary, risk rating, confidence score.
* `content_candidates`: Multi-factor content scores (0–100), curated status, confidence.
* `captions`: Informative, Emotional, and Interactive copy variants.
* `posts`: Final published messages in target channel with `target_message_id`.
* `post_metrics`: Engagement rate, views, forwards, reactions.
* `reports` & `report_snapshots`: Persistent daily report snapshots and idempotency keys.
* `alerts`: System and content alerts (`CRITICAL`, `WARNING`, `INFO`).
* `content_dna`: Top 10% post benchmarks (ideal duration, top categories, keywords).
* `simulation_scenarios`: Stored What-If candidate combinations and predicted views.

---

## 4. Existing Telegram Integration
* **MTProto Userbot Client (Telethon)**: Uses `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_SESSION_STRING`.
* **Bot API Client (HTTPX Long-Polling)**: Uses `TELEGRAM_BOT_TOKEN` for `@Muhtashamagent_bot`.
* **Channel Permissions**: Verified administrator check on startup.

---

## 5. Existing AI Integration
* Provider: `google-genai` SDK targeting model `gemini-3.6-flash`.
* Structured JSON Schema parsing with Pydantic (`AnalysisSchema`, `MultiCaptionSchema`).
* Versioned prompts located in `app/prompts/` (`analyzer.txt`, `caption.txt`, `safety.txt`, `strategist.txt`).
* Automated AI token and latency cost tracking in `ai_costs` table.

---

## 6. Existing Queue Architecture
* In-memory async worker pool with exponential backoff delay.
* Event isolation across tasks: `DOWNLOAD`, `PROCESS_MEDIA`, `PUBLISH`.
* Dead Letter Queue (`_dlq`) for unrecoverable errors.

---

## 7. Existing Frontend & Dashboard
* Responsive dark glassmorphic web dashboard in `dashboard/index.html`.
* Real-time KPI cards: Collected Media, Published Posts, Rejected Count, Average Score, AI Cost USD.
* Tabbed multi-panel view: Overview, Live Pipeline, Content Queue, Duplicate Matrix, Source Intelligence, Prediction vs Actual, AI Strategist, Simulation Sandbox.
* CSV report exporter (`/api/reports/export`).

---

## 8. Existing Features Inventory
* [x] 4-channel live source collection.
* [x] Strict duplicate detection (SHA-256 + 5-point multi-frame pHash).
* [x] Direct live target channel pre-publish verification.
* [x] Automated phone number & foreign contact cleaner.
* [x] Multi-style caption generator (Informative, Emotional, Interactive).
* [x] Automated 3x daily executive reports (08:00, 13:00, 21:00 Asia/Tashkent).
* [x] Interactive admin bot with inline action buttons.
* [x] Real-time Google Sheets webhook sync with colored statuses.
* [x] Content DNA benchmarking against top 10% posts.
* [x] What-If simulation sandbox endpoint.
* [x] 18 passed automated tests (`pytest tests/`).

---

## 9. Missing & Weak Features (To Be Extended)
1. **Visual Embeddings (CLIP / Secondary Vector)**: Currently uses pHash/dHash; adding vector embeddings will handle heavy geometric rotations and crop edits.
2. **Audio Fingerprinting**: Audio track transcription / silence / noise ratio metrics can be deeper.
3. **Formal Event Sourcing Bus**: Events currently emit to logger and database; upgrading to a dedicated `analytics_events` table will enable replayable audits.
4. **WebSocket Live Activity Stream**: Dashboard currently polls REST APIs every 15s; connecting native WebSocket streaming will give true 0ms live activity.
5. **Natural Language Admin Bot Commands**: Parsing free-form Uzbek commands (e.g. *"Bugun faqat eng sifatli 3 ta postni rejalashtir"*).

---

## 10. Technical Debt & Risks
* **SQLite Single-File Concurrency**: Works well for current scale; PostgreSQL migration script ready for $>10,000$ daily items.
* **Dual IP Session Collision**: Prevented by running MTProto client exclusively on one host.

---

## 11. Recommended Architecture & 14-Phase Roadmap

```text
PHASE 0: Repository Audit (COMPLETE)
PHASE 1: Analytics Event Infrastructure & Event Sourcing Bus
PHASE 2: Advanced Duplicate Intelligence & Multi-Vector Fingerprinting
PHASE 3: Advanced Quality Engine (Audio Clipping, Stabilization, Noise)
PHASE 4: Content Intelligence & Scoring 2.0 Dynamic Weight Calibration
PHASE 5: Audience Fit & Diversity / Fatigue Cooldown Matrix
PHASE 6: Learning Engine & Strategy Changelog Ledger
PHASE 7: Prediction Engine & Simulation Sandbox Deepening
PHASE 8: Telegram Control Bot (Natural Language Command Interpreter)
PHASE 9: Automated 08:00 / 13:00 / 21:00 Reports Hardening
PHASE 10: Professional BI Dashboard & WebSocket Stream
PHASE 11: End-to-End System Integration Verification
PHASE 12: Security Hardening & Secret Masking
PHASE 13: Stress & Load Testing (1,000 Media / Day Simulation)
PHASE 14: Final Production Deployment & Documentation
```

---

## 12. Conclusion & Next Step
The foundation is strong, well-structured, and production-operational. We are ready to proceed to **Phase 1 (Analytics Event Infrastructure)** upon user review and approval.
