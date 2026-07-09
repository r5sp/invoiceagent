"""Match invoice line items to contract tasks.

Priority order:
1. Exact task-number match (invoice states the task number, e.g. CTS bills against a PO
   line, or a task-sectioned invoice like '022A').
2. Exact/unique cost-code match.
3. Fuzzy description match (difflib) against every active contract task's description.
4. LLM-assisted correlation for anything still unmatched, when an API key is configured —
   this is the CTS 'restaurant receipt' case Joe described, where none of the above apply.
"""

from difflib import SequenceMatcher

from app.models import ContractTask
from app.services.llm_client import call_json_llm, has_valid_api_key
from pydantic import BaseModel, Field

FUZZY_MATCH_THRESHOLD = 0.42


class _Match(BaseModel):
    contract_task_id: int | None
    confidence: str  # exact | fuzzy | llm | none


def _fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _best_fuzzy_match(description: str, tasks: list[ContractTask]) -> tuple[ContractTask | None, float]:
    best_task, best_score = None, 0.0
    for task in tasks:
        score = _fuzzy_ratio(description, task.description)
        if score > best_score:
            best_task, best_score = task, score
    return best_task, best_score


class _CorrelationRow(BaseModel):
    line_index: int
    task_number: str | None = None


class _CorrelationResult(BaseModel):
    matches: list[_CorrelationRow] = Field(default_factory=list)


CORRELATION_SYSTEM_PROMPT = """You correlate time & materials invoice line items to a contract's task list. \
For each line item, pick the single best-matching task_number from the provided task list based on the \
description and cost code. If none of the tasks plausibly match, set task_number to null. Return ONLY valid \
JSON, no markdown."""


def _llm_correlate(unmatched: list[dict], tasks: list[ContractTask]) -> dict[int, str]:
    if not has_valid_api_key() or not unmatched:
        return {}
    task_list_text = "\n".join(
        f"- Task {t.task_number} (cost code {t.cost_code or 'n/a'}): {t.description}" for t in tasks
    )
    lines_text = "\n".join(
        f"{item['line_index']}. [{item.get('raw_cost_code') or 'no cost code'}] {item['description']}"
        for item in unmatched
    )
    user_prompt = (
        f"CONTRACT TASKS:\n{task_list_text}\n\nUNMATCHED LINE ITEMS:\n{lines_text}\n\n"
        'Return JSON: {"matches": [{"line_index": int, "task_number": string|null}, ...]} for every line item above.'
    )
    try:
        result = call_json_llm(CORRELATION_SYSTEM_PROMPT, user_prompt, _CorrelationResult)
    except Exception:
        return {}
    return {row.line_index: row.task_number for row in result.matches if row.task_number}


def correlate_line_items(line_items: list[dict], tasks: list[ContractTask]) -> list[dict]:
    """Mutates and returns line_items, adding 'contract_task_id' and 'correlation_confidence'."""
    active_tasks = [t for t in tasks if t.is_active] or tasks
    tasks_by_number = {t.task_number: t for t in tasks}
    tasks_by_cost_code: dict[str, list[ContractTask]] = {}
    for t in tasks:
        if t.cost_code:
            tasks_by_cost_code.setdefault(t.cost_code, []).append(t)

    unmatched_for_llm: list[dict] = []

    for idx, item in enumerate(line_items):
        raw_task_number = item.get("raw_task_number")
        raw_cost_code = item.get("raw_cost_code")
        description = item.get("description", "")

        if raw_task_number and raw_task_number in tasks_by_number:
            item["contract_task_id"] = tasks_by_number[raw_task_number].id
            item["correlation_confidence"] = "exact"
            continue

        if raw_cost_code and raw_cost_code in tasks_by_cost_code and len(tasks_by_cost_code[raw_cost_code]) == 1:
            item["contract_task_id"] = tasks_by_cost_code[raw_cost_code][0].id
            item["correlation_confidence"] = "exact"
            continue

        best_task, score = _best_fuzzy_match(description, active_tasks)
        if best_task and score >= FUZZY_MATCH_THRESHOLD:
            item["contract_task_id"] = best_task.id
            item["correlation_confidence"] = "fuzzy"
            continue

        item["contract_task_id"] = None
        item["correlation_confidence"] = "none"
        unmatched_for_llm.append({"line_index": idx, "description": description, "raw_cost_code": raw_cost_code})

    if unmatched_for_llm:
        llm_matches = _llm_correlate(unmatched_for_llm, tasks)
        for idx, task_number in llm_matches.items():
            task = tasks_by_number.get(task_number)
            if task:
                line_items[idx]["contract_task_id"] = task.id
                line_items[idx]["correlation_confidence"] = "llm"

    return line_items
