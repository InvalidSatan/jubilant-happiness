"""Shared utility helpers."""

from datetime import timezone
from zoneinfo import ZoneInfo

from flask import current_app


def is_valid_banner_id(value: str) -> bool:
    """Return True when value looks like a Banner ID (9 numeric digits)."""
    return bool(value) and value.isdigit() and len(value) == 9


def to_display_tz(dt):
    """Convert a stored datetime (naive values are treated as UTC) to the
    configured display timezone. Returns None for None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tz_name = current_app.config.get("DISPLAY_TIMEZONE", "America/New_York")
    try:
        return dt.astimezone(ZoneInfo(tz_name))
    except Exception:  # pragma: no cover - unknown tz name falls back to UTC
        return dt.astimezone(timezone.utc)


def format_local(dt, fmt="%Y-%m-%d %I:%M %p"):
    """Format a datetime in the display timezone. Used as the ``localdt`` Jinja
    filter and by CSV exports so on-screen and exported times match."""
    local = to_display_tz(dt)
    return local.strftime(fmt) if local else ""
