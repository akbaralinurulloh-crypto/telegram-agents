from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.core.config import settings
from app.core.logging import logger

from fastapi.responses import HTMLResponse
from pathlib import Path

app = FastAPI(
    title="Telegram Autonomous AI Media Creator API",
    version="2.0.0",
    description="Autonomous Telegram AI Content Intelligence, Curation, Creation and Analytics Platform"
)

# CORS sozlamalari
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

DASHBOARD_FILE = Path(__file__).resolve().parent.parent.parent / "dashboard" / "index.html"


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    if DASHBOARD_FILE.exists():
        return HTMLResponse(content=DASHBOARD_FILE.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Autonomous AI Control Center is running!</h1>")
