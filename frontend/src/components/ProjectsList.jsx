import { useEffect, useState } from "react";
import { createProject, listProjects } from "../api";
import SectionHeading from "./SectionHeading";

export default function ProjectsList({ onOpenProject }) {
  const [projects, setProjects] = useState(null);
  const [name, setName] = useState("");
  const [consultantName, setConsultantName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    listProjects().then(setProjects).catch((err) => setError(err.message));
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    setError("");
    try {
      const project = await createProject(name.trim(), consultantName.trim() || null);
      setProjects((prev) => [project, ...(prev || [])]);
      setName("");
      setConsultantName("");
      onOpenProject(project.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <main className="fs-main">
      <section className="fs-section fs-hero">
        <SectionHeading label="Invoice Agent" number={1} />
        <h1>Review invoices the way you already do — just faster.</h1>
        <p className="fs-hero-lead">
          Upload a contract's fee schedule once, then drop in each monthly invoice. Invoice Agent builds the
          billing sheet, flags overbilling and rate mismatches, and drafts the revision-request email.
        </p>
      </section>

      <section className="fs-section bg-gray">
        <div className="fs-section-inner">
          <SectionHeading label="Projects" number={2} />

          {error && <div className="status-bar error" style={{ marginBottom: "var(--fs-space-2)" }}>{error}</div>}

          {projects === null ? (
            <div className="spinner" />
          ) : projects.length === 0 ? (
            <div className="empty-state">
              <p>No projects yet — create one below to get started.</p>
            </div>
          ) : (
            <div className="project-grid">
              {projects.map((p) => (
                <div key={p.id} className="project-card" onClick={() => onOpenProject(p.id)}>
                  <h3>{p.name}</h3>
                  {p.consultant_name && <div className="meta">{p.consultant_name}</div>}
                  <div className="meta">Created {new Date(p.created_at).toLocaleDateString()}</div>
                </div>
              ))}
            </div>
          )}

          <form className="new-project-form" onSubmit={handleCreate}>
            <label>
              New project name
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Riverside Tower — Acme Consulting"
                required
              />
            </label>
            <label>
              Consultant (optional)
              <input
                type="text"
                value={consultantName}
                onChange={(e) => setConsultantName(e.target.value)}
                placeholder="e.g. Acme Consulting"
              />
            </label>
            <button type="submit" className="btn btn-primary" disabled={creating}>
              {creating ? "Creating…" : "Create project"}
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
