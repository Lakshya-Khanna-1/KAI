from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import zoneinfo

from app.config import settings

PERSONA_PATH = Path(__file__).parent / "persona.md"


def get_persona_template() -> str:
    if PERSONA_PATH.exists():
        return PERSONA_PATH.read_text(encoding="utf-8")
    return "You are KAI, a personal AI assistant."


def build_system_prompt(
    owner_name: Optional[str] = None,
    tz_name: Optional[str] = None,
    extra_context: Optional[str] = None,
    facts_summary: Optional[str] = None,
    profile_data: Optional[Dict[str, Any]] = None,
    onboarding_phase: Optional[str] = None,
    unasked_topics: Optional[list] = None,
) -> str:
    profile = profile_data or {}
    name = profile.get("name") or owner_name or settings.KAI_OWNER_NAME or "Boss"
    tz_str = profile.get("timezone") or tz_name or settings.KAI_TZ

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

    # Stated Communication Style adaptation
    comm_style = profile.get("communication_style")
    if comm_style:
        parts.append(f"\nUser Preferred Communication Style:\n{comm_style} (Adapt your tone and format accordingly).")

    # Structured Profile details
    if profile:
        prof_lines = [f"- {k}: {v}" for k, v in profile.items()]
        parts.append(f"\nUser Profile:\n" + "\n".join(prof_lines))

    if facts_summary:
        parts.append(f"\nKnown Facts & Preferences:\n{facts_summary}")

    if extra_context:
        parts.append(f"\nContext:\n{extra_context}")

    # Onboarding instructions injection if onboarding is in progress
    if onboarding_phase == "in_progress" and unasked_topics:
        parts.append(
            f"\nOnboarding Interview Active:\n"
            f"You are currently naturally getting to know {name} across sessions.\n"
            f"Topics still unasked: {', '.join(unasked_topics)}.\n"
            f"Guidelines: Ask at most 1 question per turn. Keep it casual, friendly, and non-interrogative.\n"
            f"When the user shares information on any of these topics, call 'update_user_profile(key=..., value=...)' to save it."
        )

    parts.append(
        "\nTool Usage Instructions:\n"
        "You have access to tools. When you need information or to perform an action, invoke the appropriate tool.\n"
        "Do not invent facts or make assumptions when a tool is available."
    )

    return "\n".join(parts)
