const API_BASE = import.meta.env.VITE_API_URL || "";

const jsonOpts = {
  credentials: "include",
  headers: { "Content-Type": "application/json" },
};

function parseApiError(body, fallback) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg || String(d)).join("; ");
  return fallback;
}

async function handleJson(res, fallback) {
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(parseApiError(err, fallback));
  }
  return res.json();
}

// --- auth ---
export async function fetchMe() {
  const res = await fetch(`${API_BASE}/api/auth/me`, { credentials: "include" });
  if (!res.ok) throw new Error("Not authenticated");
  return res.json();
}

export async function login(email, password) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    ...jsonOpts,
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return handleJson(res, "Login failed");
}

export async function register(email, password, name) {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    ...jsonOpts,
    method: "POST",
    body: JSON.stringify({ email, password, name }),
  });
  return handleJson(res, "Registration failed");
}

export async function logout() {
  await fetch(`${API_BASE}/api/auth/logout`, { method: "POST", credentials: "include" });
}

// --- projects ---
export async function listProjects() {
  const res = await fetch(`${API_BASE}/api/projects`, { credentials: "include" });
  return handleJson(res, "Failed to load projects");
}

export async function createProject(name, consultant_name) {
  const res = await fetch(`${API_BASE}/api/projects`, {
    ...jsonOpts,
    method: "POST",
    body: JSON.stringify({ name, consultant_name }),
  });
  return handleJson(res, "Failed to create project");
}

export async function getProject(projectId) {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}`, { credentials: "include" });
  return handleJson(res, "Failed to load project");
}

export async function deleteProject(projectId) {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}`, {
    method: "DELETE",
    credentials: "include",
  });
  return handleJson(res, "Failed to delete project");
}

// --- contracts ---
export async function uploadContract(projectId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/contracts`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  return handleJson(res, "Failed to parse contract");
}

// --- invoices ---
export async function uploadInvoice(projectId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/invoices`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  return handleJson(res, "Failed to parse invoice");
}

export async function deleteInvoice(projectId, invoiceId) {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/invoices/${invoiceId}`, {
    method: "DELETE",
    credentials: "include",
  });
  return handleJson(res, "Failed to delete invoice");
}

// --- inspection reports ---
export async function uploadInspectionReport(projectId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/inspection-reports`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  return handleJson(res, "Failed to parse inspection report");
}

// --- billing ---
export async function getBillingSummary(projectId) {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/billing-summary`, {
    credentials: "include",
  });
  return handleJson(res, "Failed to load billing summary");
}

export function getBillingSheetUrl(projectId) {
  return `${API_BASE}/api/projects/${projectId}/billing-sheet.xlsx`;
}

export async function getEmailDraft(projectId, invoiceId) {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/invoices/${invoiceId}/email-draft`, {
    credentials: "include",
  });
  return handleJson(res, "Failed to draft email");
}

// --- chat ---
export async function getChatHistory(projectId) {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/chat`, { credentials: "include" });
  return handleJson(res, "Failed to load chat history");
}

export async function sendChatMessage(projectId, message) {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/chat`, {
    ...jsonOpts,
    method: "POST",
    body: JSON.stringify({ message }),
  });
  return handleJson(res, "Failed to send message");
}
