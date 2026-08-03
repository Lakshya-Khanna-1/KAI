from datetime import datetime
import zoneinfo
from app.config import settings


def get_current_time(timezone: str | None = None) -> dict:
    """Get the current date and time in the specified or default timezone."""
    tz_str = timezone or settings.KAI_TZ
    try:
        tz = zoneinfo.ZoneInfo(tz_str)
        now = datetime.now(tz)
    except Exception:
        now = datetime.utcnow()
        tz_str = "UTC"

    return {
        "iso": now.isoformat(),
        "formatted": now.strftime("%A, %d %B %Y %I:%M %p"),
        "timezone": tz_str
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Returns the current system date and time in the configured timezone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Optional IANA timezone name, e.g. 'Asia/Kolkata' or 'UTC'."
                    }
                },
                "required": []
            }
        },
        "handler": get_current_time
    }
]
