"""Shared utility helpers."""

from datetime import date, datetime


def is_valid_banner_id(value: str) -> bool:
    """Return True when value looks like a Banner ID (9 numeric digits)."""
    return bool(value) and value.isdigit() and len(value) == 9


def _parse_event_time(value: str) -> datetime | None:
    """
    Parse a calendar timestamp into a datetime.

    Google returns either a full RFC 3339 `dateTime` for timed events or a
    bare `date` for all-day ones, so accept both and let callers decide what
    to show. Returns None for anything unparseable rather than raising, since
    a malformed event should not take down the dashboard.
    """
    if not value:
        return None
    try:
        # fromisoformat handles "...Z" only from Python 3.11 onward.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def shift_day(value: str) -> str:
    """Format a calendar start time as a short day label, e.g. "Tue 24"."""
    parsed = _parse_event_time(value)
    if parsed is None:
        return ""
    if parsed.date() == date.today():
        return "Today"
    # Build the day number by hand: the "%-d" padding flag is glibc-only and
    # raises on Windows.
    return f"{parsed.strftime('%a')} {parsed.day}"


def shift_time(value: str) -> str:
    """Format a calendar timestamp as a short clock time, e.g. "6:00pm"."""
    parsed = _parse_event_time(value)
    if parsed is None:
        return ""
    hour = parsed.hour % 12 or 12
    meridiem = "am" if parsed.hour < 12 else "pm"
    return f"{hour}:{parsed.minute:02d}{meridiem}"
