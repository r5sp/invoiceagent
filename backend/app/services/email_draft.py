"""Draft a revision-request email to the consultant, summarizing an invoice's flags."""

from app.models import Invoice, Project
from app.services.llm_client import call_chat_llm, has_valid_api_key

_SEVERITY_LABEL = {"critical": "Must resolve", "warning": "Please clarify", "info": "For your awareness"}
_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _template_body(project: Project, invoice: Invoice) -> str:
    consultant = project.consultant_name or "there"
    period = ""
    if invoice.period_start or invoice.period_end:
        period = f" for the {invoice.period_start or '?'} – {invoice.period_end or '?'} billing period"

    flags = sorted(invoice.flags, key=lambda f: _SEVERITY_ORDER.get(f.severity, 9))
    if not flags:
        return (
            f"Hi {consultant},\n\n"
            f"Invoice {invoice.invoice_number or invoice.file_name}{period} has been reviewed against the "
            "contract and no issues were found. We'll proceed with processing it for payment.\n\n"
            "Thanks,\n"
        )

    lines = [
        f"Hi {consultant},\n",
        f"We reviewed invoice {invoice.invoice_number or invoice.file_name}{period} against the contract and "
        "have a few items that need to be addressed before it can be processed:\n",
    ]
    for severity in ("critical", "warning", "info"):
        group = [f for f in flags if f.severity == severity]
        if not group:
            continue
        lines.append(f"\n{_SEVERITY_LABEL[severity]}:")
        for f in group:
            lines.append(f"  - {f.message}")

    lines.append(
        "\nCould you please revise and resubmit, or let us know if any of the above is a misunderstanding on "
        "our end? Happy to hop on a call if that's easier.\n"
    )
    lines.append("Thanks,\n")
    return "\n".join(lines)


def draft_revision_email(project: Project, invoice: Invoice) -> dict:
    subject = f"Invoice {invoice.invoice_number or invoice.file_name} — Revisions Needed"
    if not invoice.flags:
        subject = f"Invoice {invoice.invoice_number or invoice.file_name} — Approved"
    body = _template_body(project, invoice)

    if has_valid_api_key() and invoice.flags:
        try:
            polished = call_chat_llm(
                "You lightly polish professional project-management emails for tone and clarity. "
                "Preserve every fact, dollar amount, date, and bullet point exactly — do not add, remove, or "
                "reword any factual claim. Only improve phrasing, transitions, and formatting. Return only the "
                "email body, no subject line.",
                [{"role": "user", "content": body}],
            )
            if polished.strip():
                body = polished.strip()
        except Exception:
            pass

    return {"subject": subject, "body": body}
