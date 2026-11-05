from pathlib import Path

_DIR = Path(__file__).resolve().parents[2] / "prompts"


def load_prompt(name: str, **values: str) -> str:
    """prompts/<name>.md ni o'qiydi; {{kalit}} o'rniga qiymat qo'yadi (JSON qavslari bilan to'qnashmaydi)."""
    text = (_DIR / f"{name}.md").read_text(encoding="utf-8")
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    return text
