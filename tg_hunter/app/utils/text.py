TG_LIMIT = 4000


def split_message(text: str, limit: int = TG_LIMIT) -> list[str]:
    """Telegram xabar limitiga (4096) sig'maydigan matnni qator chegarasida bo'laklaydi."""
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit and cur:
            out.append(cur)
            cur = ""
        cur += line[:limit] + "\n"
    return out + ([cur] if cur.strip() else [])
