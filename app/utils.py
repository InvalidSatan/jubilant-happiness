"""Shared utility helpers."""


def is_valid_banner_id(value: str) -> bool:
    """Return True when value looks like a Banner ID (9 numeric digits)."""
    return bool(value) and value.isdigit() and len(value) == 9
