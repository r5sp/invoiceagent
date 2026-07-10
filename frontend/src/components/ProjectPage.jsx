import { useCallback, useEffect, useState } from "react";
import {
  deleteInvoice,
  getBillingSheetUrl,
  getBillingSummary,
  getProject,
  uploadContract,
  uploadInspectionReport,
  uploadInvoice,
} from "../api";
import SectionHeading from "./SectionHeading";
import UploadDropzone from "./UploadDropzone";
import BillingSummaryTable from "./BillingSummaryTable";
import InvoiceCard from "./InvoiceCard";
import ChatPanel from "./ChatPanel";

export default function ProjectPage({ projectId, onBack }) {
  const [project, setProject] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [p, s] = await Promise.all([getProject(projectId), getBillingSummary(projectId)]);
      setProject(p);
      setSummary(s);
    } catch (err) {
      setError(err.message);
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (error) {
    return (
      <main className="fs-main">
        <div className="fs-section">
          <div className="status-bar error">{error}</div>
        </div>
      </main>
    );
  }

  if (!project) {
    return (
      <main className="fs-main">
        <div className="fs-section" style={{ display: "flex", justifyContent: "center" }}>
          <div className="spinner" />
        </div>
      </main>
    );
  }

  const contract = project.contracts[project.contracts.length - 1];
  const invoices = [...project.invoices].sort((a, b) =>
    (a.period_start || a.uploaded_at).localeCompare(b.period_start || b.uploaded_at)
  );

  return (
    <div className="app-shell">
      <div className="app-main">
        <main>
          <div className="breadcrumb">
            <button type="button" onClick={onBack}>
              ← Projects
            </button>
            <span>/</span>
            <span>{project.name}</span>
          </div>

          <section className="fs-section-inner" style={{ marginBottom: "var(--fs-space-4)" }}>
            <h1 style={{ fontFamily: "Origin, Arbeit, sans-serif", fontSize: "2rem", marginBottom: 4 }}>
              {project.name}
            </h1>
            {project.consultant_name && (
              <p style={{ color: "var(--fs-light-blue)" }}>{project.consultant_name}</p>
            )}
          </section>

          <section className="fs-section-inner" style={{ marginBottom: "var(--fs-space-4)" }}>
            <SectionHeading label="Contract" number={1} />
            {contract ? (
              <div className="card">
                <div className="card-title">{contract.file_name}</div>
                <p>
                  {contract.label && <strong>{contract.label} — </strong>}
                  {contract.tasks.length} tasks
                  {contract.not_to_exceed_total != null &&
                    ` · Not-to-exceed $${contract.not_to_exceed_total.toLocaleString()}`}
                </p>
                <div style={{ marginTop: "var(--fs-space-2)" }}>
                  <UploadDropzone
                    compact
                    label="Replace with an updated contract/addendum"
                    sublabel="Drop the latest PDF or DOCX to update the fee schedule"
                    onUpload={async (file) => {
                      await uploadContract(projectId, file);
                      await refresh();
                    }}
                  />
                </div>
              </div>
            ) : (
              <UploadDropzone
                label="Drop the contract here (optional)"
                sublabel="PDF or DOCX — the consultant's agreement / Exhibit B fee schedule. Optional: invoices analyze on their own; add the contract for full rate & cost-code cross-checks."
                onUpload={async (file) => {
                  await uploadContract(projectId, file);
                  await refresh();
                }}
              />
            )}
          </section>

          <section className="fs-section-inner" style={{ marginBottom: "var(--fs-space-4)" }}>
            <div className="section-toolbar">
              <SectionHeading label="Billing sheet" number={2} />
              {summary?.rows?.length > 0 && (
                <a className="btn btn-secondary btn-sm" href={getBillingSheetUrl(projectId)} download>
                  Download Excel
                </a>
              )}
            </div>
            <BillingSummaryTable summary={summary} />
          </section>

          <section className="fs-section-inner" style={{ marginBottom: "var(--fs-space-4)" }}>
            <SectionHeading label="Invoices" number={3} />
            {!contract && (
              <p style={{ color: "var(--fs-light-blue)", marginBottom: "var(--fs-space-2)" }}>
                Drop invoices here — they're analyzed on their own (% billed, 75%/at-limit flags, math checks).
                Add the contract above for full cross-checks against the fee schedule.
              </p>
            )}
            <div style={{ marginBottom: "var(--fs-space-2)" }}>
              <UploadDropzone
                compact
                label="Drop a monthly invoice here"
                sublabel="PDF or DOCX — one invoice at a time, creates a new tab in the billing sheet"
                onUpload={async (file) => {
                  await uploadInvoice(projectId, file);
                  await refresh();
                }}
              />
            </div>
            {invoices.length === 0 ? (
              <div className="empty-state">
                <p>No invoices uploaded yet.</p>
              </div>
            ) : (
              invoices
                .slice()
                .reverse()
                .map((inv) => (
                  <InvoiceCard
                    key={inv.id}
                    invoice={inv}
                    onDelete={async (id) => {
                      await deleteInvoice(projectId, id);
                      await refresh();
                    }}
                  />
                ))
            )}
          </section>

          <section className="fs-section-inner" style={{ marginBottom: "var(--fs-space-4)" }}>
            <SectionHeading label="Inspection / field reports" number={4} />
            <p style={{ color: "var(--fs-light-blue)", marginBottom: "var(--fs-space-2)" }}>
              Optional — upload daily or monthly field reports so invoiced inspection dates can be cross-checked
              against them.
            </p>
            <UploadDropzone
              compact
              label="Drop a field/inspection report here"
              sublabel="PDF or DOCX"
              onUpload={async (file) => {
                await uploadInspectionReport(projectId, file);
                await refresh();
              }}
            />
            {project.inspection_reports?.length > 0 && (
              <ul style={{ marginTop: "var(--fs-space-2)", fontSize: "0.875rem" }}>
                {project.inspection_reports.map((r) => (
                  <li key={r.id}>{r.file_name}</li>
                ))}
              </ul>
            )}
          </section>
        </main>
      </div>
      <ChatPanel projectId={projectId} />
    </div>
  );
}
