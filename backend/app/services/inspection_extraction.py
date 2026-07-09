"""Extract the set of dates field/inspection work actually occurred from a report,
so invoiced inspection dates can be cross-checked against it."""

import re

from app.schemas import InspectionDatesExtract
from app.services.llm_client import call_json_llm, has_valid_api_key
from app.services.parsing_utils import parse_date

_DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b")

SYSTEM_PROMPT = """You extract the set of calendar dates on which fieldwork/inspection/sampling actually \
occurred from a field report, daily log, or lab report. Only include dates where the report indicates work \
was performed (e.g. a sample was collected, an inspection occurred) — exclude dates explicitly marked as \
'not occurring', blank, or with no data. Return ONLY valid JSON, no markdown."""

USER_TEMPLATE = """Extract the inspection/field-work dates from this report. Return JSON:
{{
  "period_start": string|null,
  "period_end": string|null,
  "inspection_dates": [string, ...]
}}

Dates must be ISO format (YYYY-MM-DD).

REPORT TEXT:
---
{report_text}
---"""


def extract_inspection_dates_heuristic(raw_text: str) -> InspectionDatesExtract:
    dates: set[str] = set()
    for m in _DATE_RE.finditer(raw_text):
        d = parse_date(m.group(1))
        if d:
            dates.add(d.isoformat())
    sorted_dates = sorted(dates)
    return InspectionDatesExtract(
        period_start=sorted_dates[0] if sorted_dates else None,
        period_end=sorted_dates[-1] if sorted_dates else None,
        inspection_dates=sorted_dates,
    )


def extract_inspection_dates(raw_text: str) -> InspectionDatesExtract:
    if has_valid_api_key():
        try:
            return call_json_llm(
                SYSTEM_PROMPT, USER_TEMPLATE.format(report_text=raw_text), InspectionDatesExtract
            )
        except Exception:
            pass
    return extract_inspection_dates_heuristic(raw_text)
