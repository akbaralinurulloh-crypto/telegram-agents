"""Render bepul 'web service' uchun kichik HTTP server va o'zini uyg'oq tutish.

Render web xizmati $PORT da HTTP javob berishi shart. Bepul reja esa 15 daqiqa kiruvchi trafik bo'lmasa uxlaydi
(uxlaganda agent Telegram yangiliklarini ololmaydi). Shuning uchun:
  1) /health ga 200 javob beramiz;
  2) RENDER_EXTERNAL_URL bor bo'lsa, har 10 daqiqada o'z manzilimizga so'rov yuboramiz (uyg'oq turish uchun).
Pullik 'worker' yoki VPS'da bu kerak emas: PORT berilmasa, hech narsa ishga tushmaydi.
"""
from __future__ import annotations

import asyncio

import aiohttp
from aiohttp import web

from app.utils.logging import get_logger

log = get_logger("health")
HITS = web.AppKey("hits", list)  # [soni]: ro'yxat ichini o'zgartiramiz, ilova holatini emas


async def _health(request: web.Request) -> web.Response:
    request.app[HITS][0] += 1
    return web.json_response({"ok": True, "service": "tg-hunter"})


async def start_health_server(port: int, host: str = "0.0.0.0") -> web.AppRunner:
    app = web.Application()
    app[HITS] = [0]
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    log.info("health_server_started", port=port)
    return runner


def server_port(runner: web.AppRunner) -> int:
    return runner.addresses[0][1]


async def keep_alive_loop(base_url: str, every_seconds: float = 600.0) -> None:
    """Har `every_seconds` da o'z /health manziliga so'rov yuboradi (Render uxlab qolmasligi uchun)."""
    url = base_url.rstrip("/") + "/health"
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            try:
                async with session.get(url) as resp:
                    await resp.read()
            except Exception as exc:  # tarmoq xatosi: keyingi urinishda qayta
                log.warning("keep_alive_failed", error=str(exc)[:120])
            await asyncio.sleep(every_seconds)
