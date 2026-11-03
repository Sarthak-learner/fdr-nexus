from datetime import date
from typing import Optional, Tuple
from ..config import MATURITY_REMINDER_THRESHOLDS, WARN_DAYS

MATURITY_LABELS = {
    "active": "Active",
    "due_within_30_days": "Due within 30 days",
    "due_within_15_days": "Due within 15 days",
    "due_within_7_days": "Due within 7 days",
    "due_tomorrow": "Due tomorrow",
    "matured_today": "Matured today",
    "overdue": "Overdue",
}


def maturity_details(maturity: date, today: Optional[date] = None, warn_days: int = WARN_DAYS) -> dict:
    """Return one authoritative, precedence-ordered maturity classification.

    The legacy status is retained for existing API consumers. The detailed
    category is more precise and always wins from most urgent to least urgent.
    """
    today = today or date.today()
    days = (maturity - today).days
    if days < 0:
        category = "overdue"
    elif days == 0:
        category = "matured_today"
    elif days == 1:
        category = "due_tomorrow"
    elif days <= 7:
        category = "due_within_7_days"
    elif days <= 15:
        category = "due_within_15_days"
    elif days <= 30:
        category = "due_within_30_days"
    else:
        category = "active"

    legacy = "expired" if days < 0 else "expiring_soon" if days <= warn_days else "valid"
    return {
        "maturity_status": legacy,
        "maturity_category": category,
        "maturity_label": MATURITY_LABELS[category],
        "days_to_maturity": days,
    }


def maturity_status(maturity: date, today: Optional[date] = None, warn_days: int = WARN_DAYS) -> Tuple[str, int]:
    """Backward-compatible coarse status used by existing consumers."""
    details = maturity_details(maturity, today=today, warn_days=warn_days)
    return details["maturity_status"], details["days_to_maturity"]


def reminder_details(details: dict) -> tuple[str | None, int | None, str | None]:
    """Map one maturity result to the configured reminder threshold."""
    days = details["days_to_maturity"]
    if days < 0:
        return "overdue", -1, "Overdue"
    if days == 0:
        return "matured_today", 0, "Matured today"
    if days == 1:
        return "due_tomorrow", 1, "Due tomorrow"
    # Thresholds are configured from broadest to most urgent (for example,
    # 30, 15, 7, 1). Select the smallest matching window so classifications
    # remain mutually exclusive and preserve the documented precedence.
    for threshold in reversed(MATURITY_REMINDER_THRESHOLDS):
        if days <= threshold:
            return f"due_within_{threshold}_days", threshold, f"Due within {threshold} days"
    return None, None, None
