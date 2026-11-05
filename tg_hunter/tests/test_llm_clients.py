import json

import httpx
import pytest

from app.config import AppConfig, Settings
from app.llm.anthropic import AnthropicClient
from app.llm.base import LLMError, parse_json_object, sniff_mime
from app.llm.factory import build_llm
from app.llm.gemini import GeminiClient

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def gemini_ok(obj):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}, "finishReason": "STOP"}]}


class Recorder:
    def __init__(self, responses):
        self.responses, self.requests, self.sleeps = list(responses), [], []

    def transport(self):
        def handler(req: httpx.Request):
            self.requests.append(req)
            r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
            return r if isinstance(r, httpx.Response) else httpx.Response(200, json=r)

        return httpx.MockTransport(handler)

    async def sleep(self, s):
        self.sleeps.append(s)


def gem(rec, **kw):
    return GeminiClient("KEY", "gemini-test", transport=rec.transport(), sleep=rec.sleep, **kw)


async def test_gemini_request_shape_and_parse():
    rec = Recorder([gemini_ok({"a": 1})])
    out = await gem(rec).generate_json(system="SYS", user="USER", images=[PNG])
    assert out == {"a": 1}
    req = rec.requests[0]
    assert req.url.path.endswith("/models/gemini-test:generateContent")
    assert req.headers["x-goog-api-key"] == "KEY"
    body = json.loads(req.content)
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    parts = body["contents"][0]["parts"]
    assert parts[0] == {"text": "USER"} and parts[1]["inlineData"]["mimeType"] == "image/png"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "KEY" not in req.url.query.decode()  # kalit URL'da emas, sarlavhada


async def test_gemini_accepts_fenced_json():
    rec = Recorder([{"candidates": [{"content": {"parts": [{"text": '```json\n{"x": 2}\n```'}]}}]}])
    assert await gem(rec).generate_json(system="s", user="u") == {"x": 2}


async def test_gemini_retries_429_with_retry_after_then_succeeds():
    rec = Recorder([httpx.Response(429, headers={"retry-after": "7"}, text="slow"), httpx.Response(503, text="x"), gemini_ok({"ok": 1})])
    assert await gem(rec).generate_json(system="s", user="u") == {"ok": 1}
    assert len(rec.requests) == 3 and rec.sleeps[0] == 7.0 and rec.sleeps[1] > 0


async def test_gemini_gives_up_after_max_retries():
    rec = Recorder([httpx.Response(500, text="boom")])
    with pytest.raises(LLMError, match="HTTP 500"):
        await gem(rec, max_retries=2).generate_json(system="s", user="u")
    assert len(rec.requests) == 3


async def test_gemini_falls_back_to_next_model_when_primary_busy():
    def handler(req):
        return httpx.Response(503, text="busy") if "primary" in req.url.path else httpx.Response(200, json=gemini_ok({"ok": 1}))

    rec = Recorder([])
    c = GeminiClient("K", "primary", fallback_models=["backup"], max_retries=1, transport=httpx.MockTransport(handler), sleep=rec.sleep)
    assert await c.generate_json(system="s", user="u") == {"ok": 1}
    assert c.last_model_used == "backup" and len(rec.sleeps) == 1


async def test_gemini_all_models_busy_raises():
    rec = Recorder([httpx.Response(503, text="busy")])
    c = GeminiClient("K", "a", fallback_models=["b"], max_retries=0, transport=rec.transport(), sleep=rec.sleep)
    with pytest.raises(LLMError):
        await c.generate_json(system="s", user="u")
    assert [r.url.path.split("/")[-1] for r in rec.requests] == ["a:generateContent", "b:generateContent"]


async def test_gemini_client_error_not_retried():
    rec = Recorder([httpx.Response(400, text="bad key")])
    with pytest.raises(LLMError, match="400"):
        await gem(rec).generate_json(system="s", user="u")
    assert len(rec.requests) == 1


async def test_gemini_network_error_retried():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json=gemini_ok({"ok": True}))

    rec = Recorder([])
    c = GeminiClient("K", "m", transport=httpx.MockTransport(handler), sleep=rec.sleep)
    assert await c.generate_json(system="s", user="u") == {"ok": True} and calls["n"] == 3


@pytest.mark.parametrize(
    "resp",
    [{"candidates": []}, {"promptFeedback": {"blockReason": "SAFETY"}}, {"candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}]},
     {"candidates": [{"content": {"parts": [{"text": "salom"}]}}]}, {"candidates": [{"content": {"parts": [{"text": "[1,2]"}]}}]}],
)
async def test_gemini_bad_responses_raise(resp):
    with pytest.raises(LLMError):
        await gem(Recorder([resp])).generate_json(system="s", user="u")


async def test_anthropic_tool_use_flow():
    rec = Recorder([{"content": [{"type": "tool_use", "name": "respond", "input": {"caption": "salom"}}], "stop_reason": "tool_use"}])
    c = AnthropicClient("AKEY", "claude-test", transport=rec.transport(), sleep=rec.sleep)
    assert await c.generate_json(system="SYS", user="U", images=[PNG]) == {"caption": "salom"}
    req = rec.requests[0]
    body = json.loads(req.content)
    assert req.headers["x-api-key"] == "AKEY" and req.headers["anthropic-version"]
    assert body["model"] == "claude-test" and body["tool_choice"] == {"type": "tool", "name": "respond"}
    assert body["messages"][0]["content"][0]["source"]["media_type"] == "image/png"


async def test_anthropic_without_tool_use_raises():
    rec = Recorder([{"content": [{"type": "text", "text": "hi"}], "stop_reason": "end_turn"}])
    c = AnthropicClient("K", "m", transport=rec.transport(), sleep=rec.sleep)
    with pytest.raises(LLMError):
        await c.generate_json(system="s", user="u")


def test_factory_picks_provider_and_requires_key():
    gcfg = AppConfig.model_validate({"llm": {"provider": "gemini"}})
    acfg = AppConfig.model_validate({"llm": {"provider": "anthropic"}})
    assert isinstance(build_llm(Settings(_env_file=None, GEMINI_API_KEY="k"), gcfg), GeminiClient)
    assert isinstance(build_llm(Settings(_env_file=None, ANTHROPIC_API_KEY="k"), acfg), AnthropicClient)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        build_llm(Settings(_env_file=None), gcfg)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        build_llm(Settings(_env_file=None), acfg)


def test_helpers():
    assert sniff_mime(PNG) == "image/png" and sniff_mime(b"\xff\xd8\xff") == "image/jpeg"
    assert sniff_mime(b"RIFF\0\0\0\0WEBPxx") == "image/webp"
    assert parse_json_object(' {"a": 1} ') == {"a": 1}
