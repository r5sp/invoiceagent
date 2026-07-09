"""Open-ended chat over a project's full contract + invoice + review-flag context.

The whole point (per Joe/Ronit's spec) is that this memory is scoped to the project —
every invoice, the contract, and every flag raised stays available to the chat for the
life of the project, so follow-up questions don't require re-explaining anything.
"""

from app.models import Project
from app.services.llm_client import call_chat_llm, has_valid_api_key
from app.services.review_engine import latest_contract, summarize_billing

CHAT_SYSTEM_PROMPT = """You are Joe's invoice-review assistant for Fifth Space. You help review consultant \
invoices against their contract, explain flagged issues, and answer questions about billing status. You have \
full context on the contract's fee schedule, every invoice submitted, and every issue already flagged below. \
Be concise, cite specific task numbers and dollar amounts, and say clearly when something isn't in the provided \
context rather than guessing."""


def build_project_context(project: Project) -> str:
    contract = latest_contract(project)
    parts = [f"PROJECT: {project.name}", f"CONSULTANT: {project.consultant_name or 'n/a'}"]

    if contract:
        parts.append(f"\nCONTRACT: {contract.file_name} ({contract.label or 'n/a'})")
        if contract.not_to_exceed_total:
            parts.append(f"Agreement not-to-exceed total: ${contract.not_to_exceed_total:,.2f}")
        parts.append("\nFEE SCHEDULE:")
        for t in contract.tasks:
            status = "" if t.is_active else f" [INACTIVE — {t.notes or 'superseded'}]"
            rate = f" (${t.unit_rate:,.2f}/{t.unit_type})" if t.unit_rate else ""
            parts.append(
                f"  Task {t.task_number} [{t.cost_code or 'no code'}] {t.description[:80]}{rate} — "
                f"${t.estimated_fee:,.2f}{status}"
            )

        summary = summarize_billing(project)
        parts.append("\nBILLING STATUS (as of the latest invoice):")
        for r in summary.rows:
            parts.append(
                f"  Task {r.task_number}: ${r.billed_to_date:,.2f} of ${r.estimated_fee:,.2f} "
                f"({r.pct_billed:.1%}) — ${r.remaining:,.2f} remaining"
            )
        parts.append(
            f"  TOTAL: ${summary.total_billed_to_date:,.2f} of ${summary.contract_total:,.2f} billed, "
            f"${summary.total_remaining:,.2f} remaining"
        )
    else:
        parts.append("\nNo contract has been uploaded for this project yet.")

    parts.append("\nINVOICES:")
    for inv in sorted(project.invoices, key=lambda i: (i.period_start or i.uploaded_at.date(), i.id)):
        parts.append(
            f"  Invoice {inv.invoice_number or inv.file_name} — {inv.period_start or '?'} to "
            f"{inv.period_end or '?'} — total ${inv.total_amount or 0:,.2f} — {len(inv.flags)} flag(s)"
        )
        for f in inv.flags:
            parts.append(f"    [{f.severity.upper()}/{f.rule_code}] {f.message}")

    if project.inspection_reports:
        parts.append("\nINSPECTION/FIELD REPORTS ON FILE:")
        for r in project.inspection_reports:
            parts.append(f"  {r.file_name} ({r.period_start or '?'} to {r.period_end or '?'})")

    return "\n".join(parts)


def get_chat_reply(project: Project, history: list[dict], user_message: str) -> str:
    if not has_valid_api_key():
        return (
            "Chat requires an OpenAI API key — set OPENAI_API_KEY on the server to enable open-ended Q&A "
            "about this project."
        )

    context = build_project_context(project)
    system_prompt = f"{CHAT_SYSTEM_PROMPT}\n\n---PROJECT CONTEXT---\n{context}\n---END CONTEXT---"
    messages = [*history, {"role": "user", "content": user_message}]
    try:
        return call_chat_llm(system_prompt, messages)
    except Exception as exc:
        return f"Sorry, I hit an error answering that: {exc}"
