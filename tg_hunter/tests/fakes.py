from __future__ import annotations

from app.llm.base import LLMError


class FakeLLM:
    """Rolga (prompt boshidagi `# ROLE: X`) qarab navbatdagi javobni qaytaradi. Chaqiruvlar `calls` da."""

    def __init__(self, scorer=(), captioner=(), validator=()):
        self.queues = {"SCORER": list(scorer), "CAPTIONER": list(captioner), "VALIDATOR": list(validator)}
        self.calls: list[dict] = []

    async def generate_json(self, *, system, user, images=()):
        role = system.split("# ROLE:", 1)[1].split()[0]
        self.calls.append({"role": role, "user": user, "images": list(images)})
        queue = self.queues[role]
        if not queue:
            raise AssertionError(f"{role} uchun javob qolmadi")
        item = queue.pop(0) if len(queue) > 1 else queue[0]  # oxirgisi takrorlanadi
        if isinstance(item, Exception):
            raise item
        return item

    def count(self, role: str) -> int:
        return sum(c["role"] == role for c in self.calls)


GOOD_VERDICT = {"supported": True, "unsupported_claims": [], "religious_quote": False, "uzbek_latin": True, "extra_content": False}
