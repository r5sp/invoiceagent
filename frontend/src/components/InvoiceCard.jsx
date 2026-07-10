import { useState } from "react";
import { getEmailDraft } from "../api";

function fmt(n) {
  if (n === null || n === undefined) return "—";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const SEVERITY_ORDER = { critical: 0, warning: 1, info: 2 };

export default function InvoiceCard({ invoice, onDelete, hasContract = false }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const criticalCount = invoice.flags.filter((f) => f.severity === "critical").length;
  const warningCount = invoice.flags.filter((f) => f.severity === "warning").length;
  const sortedFlags = [...invoice.flags].sort(
    (a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
  );

  const loadDraft = async () => {
    if (draft) return;
    setDraftLoading(true);
    try {
      const d = await getEmailDraft(invoice.project_id, invoice.id);
      setDraft(d);
    } catch (err) {
      setDraft({ subject: "Error", body: err.message });
    } finally {
      setDraftLoading(false);
    }
  };

  const copyDraft = () => {
    if (!draft) return;
    navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="invoice-card">
      <div className="invoice-card-header" onClick={() => setOpen((o) => !o)}>
        <div>
          <div className="invoice-card-title">
            {invoice.invoice_number ? `Invoice ${invoice.invoice_number}` : invoice.file_name}
          </div>
          <div className="invoice-card-meta">
            {invoice.period_start && invoice.period_end
              ? `${invoice.period_start} → ${invoice.period_end}`
              : invoice.file_name}
            {" · "}
            {fmt(invoice.total_amount)}
            {" · "}
            {invoice.invoice_format === "task_correlated" ? "Billing sheet" : "T&M receipt"}
          </div>
        </div>
        <div className="invoice-card-flags">
          {criticalCount > 0 && <span className="badge-severity critical">{criticalCount} critical</span>}
          {warningCount > 0 && <span className="badge-severity warning">{warningCount} warning</span>}
          {criticalCount === 0 && warningCount === 0 && <span className="badge-severity info">Clean</span>}
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(invoice.id);
            }}
          >
            Delete
          </button>
        </div>
      </div>

      {open && (
        <div className="invoice-card-body">
          {sortedFlags.length === 0 ? (
            <p style={{ color: "var(--fs-light-blue)", fontSize: "0.875rem" }}>
              {hasContract ? "No issues found — matches the contract." : "No issues found — invoice checks passed."}
            </p>
          ) : (
            <div style={{ marginBottom: "var(--fs-space-2)" }}>
              {sortedFlags.map((f) => (
                <div key={f.id} className="flag-row">
                  <span className={`badge-severity ${f.severity}`}>{f.rule_code.replace(/_/g, " ")}</span>
                  <span>{f.message}</span>
                </div>
              ))}
            </div>
          )}

          <div className="btn-group" style={{ marginTop: 0 }}>
            <button type="button" className="btn btn-secondary btn-sm" onClick={loadDraft} disabled={draftLoading}>
              {draftLoading ? "Drafting…" : "Draft revision email"}
            </button>
            {draft && (
              <button type="button" className="btn btn-secondary btn-sm" onClick={copyDraft}>
                {copied ? "Copied!" : "Copy to clipboard"}
              </button>
            )}
          </div>

          {draft && (
            <div className="email-draft-box">
              <strong>Subject: {draft.subject}</strong>
              {"\n\n"}
              {draft.body}
            </div>
          )}

          {invoice.line_items.length > 0 && (
            <details style={{ marginTop: "var(--fs-space-2)" }}>
              <summary style={{ cursor: "pointer", fontSize: "0.875rem", fontWeight: 600 }}>
                {invoice.line_items.length} line item{invoice.line_items.length === 1 ? "" : "s"}
              </summary>
              <div className="billing-table-wrap" style={{ marginTop: "var(--fs-space-1)" }}>
                <table className="billing-table">
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Description</th>
                      <th>Date</th>
                      <th>Qty</th>
                      <th>Rate</th>
                      <th>Amount</th>
                      <th>{hasContract ? "Matched?" : "Task"}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoice.line_items.map((li) => (
                      <tr key={li.id}>
                        <td>{li.raw_task_number || "—"}</td>
                        <td className="wrap">{li.description}</td>
                        <td>{li.work_date || "—"}</td>
                        <td>{li.quantity ?? "—"}</td>
                        <td>{li.unit_rate != null ? fmt(li.unit_rate) : "—"}</td>
                        <td>{fmt(li.billed_this_period ?? li.amount)}</td>
                        <td>
                          {li.contract_task_id ? (
                            <span className="badge badge-review-no">matched</span>
                          ) : hasContract ? (
                            <span className="badge-severity critical">unmatched</span>
                          ) : (
                            <span style={{ color: "var(--fs-light-blue)" }}>—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
