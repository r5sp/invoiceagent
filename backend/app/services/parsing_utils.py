"""Shared parsing helpers: currency, percent, and date string normalization."""

import calendar
import re
from datetime import date, datetime

_CURRENCY_RE = re.compile(r"[^0-9.\-()]")


def parse_currency(raw: str | None) -> float | None:
    """Parse strings like '$ 1,234.56', '(38,500.00)', '$-', '0.0%'->None into a float.

    Only strips parens as accounting-negative notation when they wrap the whole cleaned
    number (e.g. '(38,500.00)') — an unmatched trailing paren (e.g. a wrapped sentence
    fragment like '$700)') is NOT a real amount and should fail to parse rather than
    silently returning a wrong positive number.
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text or text in {"-", "$-", "$ -", "N/A"}:
        return 0.0
    cleaned = _CURRENCY_RE.sub("", text)
    if not cleaned or cleaned in {"-", "."}:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -value if negative and value > 0 else value


def parse_percent(raw: str | None) -> float | None:
    """Parse '184.6%' -> 1.846, '75' -> 0.75 (assumes already-fractional if <=1.5)."""
    if raw is None:
        return None
    text = raw.strip().replace("%", "")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value / 100.0


_DATE_FORMATS = [
    "%m/%d/%Y",
    "%m/%d/%y",
    "%Y-%m-%d",
    "%B %d, %Y",
    "%b %d, %Y",
    "%m-%d-%Y",
    "%m-%d-%y",
]


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # ISO-ish "2026-04-06T00:00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


_FULL_RANGE_RE = re.compile(
    r"([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})?\s*-\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})", re.IGNORECASE
)
_MONTH_RANGE_RE = re.compile(r"([A-Za-z]+)\s*-\s*([A-Za-z]+),?\s*(\d{4})", re.IGNORECASE)


def parse_period_range(raw: str | None) -> tuple[date | None, date | None]:
    """Parse a billing-period range string into (start, end) dates.

    Handles 'April 1 - June 30, 2026' and 'April - June, 2026' style ranges.
    """
    if not raw:
        return None, None
    text = raw.strip()

    if m := _FULL_RANGE_RE.search(text):
        month1, day1, year1, month2, day2, year2 = m.groups()
        year1 = year1 or year2
        start = parse_date(f"{month1} {day1}, {year1}")
        end = parse_date(f"{month2} {day2}, {year2}")
        return start, end

    if m := _MONTH_RANGE_RE.search(text):
        month1, month2, year = m.groups()
        try:
            start_month = datetime.strptime(month1.strip(), "%B").month
        except ValueError:
            try:
                start_month = datetime.strptime(month1.strip(), "%b").month
            except ValueError:
                return None, None
        try:
            end_month = datetime.strptime(month2.strip(), "%B").month
        except ValueError:
            try:
                end_month = datetime.strptime(month2.strip(), "%b").month
            except ValueError:
                return None, None
        yr = int(year)
        start = date(yr, start_month, 1)
        end = date(yr, end_month, calendar.monthrange(yr, end_month)[1])
        return start, end

    return None, None


def clean_cell(raw: str | None) -> str:
    if raw is None:
        return ""
    return re.sub(r"\s+", " ", raw.replace("\n", " ")).strip()
