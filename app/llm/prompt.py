from datetime import datetime
from pathlib import Path
import zoneinfo

from app.config import settings

PERSONA_PATH = Path(__file__).parent / "persona.md"


def get_persona_template() -> str:
    if PERSONA_PATH.exists():
        return PERSONA_PATH.read_text(encoding="utf-8")
    return "You are KAI, a personal AI assistant."


def build_system_prompt(
    owner_name: str | None = None,
    tz_name: str | None = None,
    extra_context: str | None = None,
    facts_summary: str | None = None,
) -> str:
    name = owner_name or settings.KAI_OWNER_NAME or "Boss"
    tz_str = tz_name or settings.KAI_TZ

    try:
        tz = zoneinfo.ZoneInfo(tz_str)
        now = datetime.now(tz)
    except Exception:
        now = datetime.utcnow()

    time_formatted = now.strftime("%A, %d %b %Y %H:%M:%S %Z")

    template = get_persona_template()
    persona_rendered = template.format(owner_name=name)

    parts = [
        persona_rendered.strip(),
        f"\nCurrent Time: {time_formatted}",
        f"Timezone: {tz_str}",
    ]

    if facts_summary:
        parts.append(f"\nKnown Facts & Preferences:\n{facts_summary}")

    if extra_context:
        parts.append(f"\nContext:\n{extra_context}")

    parts.append(
        "\nTool Usage Instructions:\n"
        "You have access to tools. When you need information or to perform an action, invoke the appropriate tool.\n"
        "Do not invent facts or make assumptions when a tool is available."
    )

    return "\n".join(parts)
