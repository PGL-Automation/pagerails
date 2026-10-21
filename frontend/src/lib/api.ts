/**
 * API client — talks to the FastAPI backend at NEXT_PUBLIC_API_URL.
 * Falls back to the Next.js API routes if the backend is unavailable.
 */

// Dev: NEXT_PUBLIC_API_URL=http://localhost:8000 (direct to FastAPI)
// Prod: NEXT_PUBLIC_API_URL="" or unset → relative paths, Nginx routes /api/* to FastAPI
export const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

// Token is stored in sessionStorage on the client, or read from headers server-side.
export function getToken(): string {
  if (typeof window !== "undefined") {
    return sessionStorage.getItem("recon_token") ?? "";
  }
  return "";
}

export async function apiFetch<T>(
  path: string,
  opts: RequestInit = {},
  token?: string,
): Promise<T> {
  const t = token ?? getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(t ? { Authorization: `Bearer ${t}` } : {}),
      ...(opts.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `API error ${res.status}`);
  }
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(email: string, password: string) {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch(`${BASE}/api/auth/token`, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  if (!res.ok) throw new Error("Invalid credentials");
  const data = await res.json();
  if (typeof window !== "undefined") {
    sessionStorage.setItem("recon_token", data.access_token);
    sessionStorage.setItem("recon_user", JSON.stringify({
      name: data.name, role: data.role, permissions: data.permissions ?? []
    }));
  }
  return data as { access_token: string; name: string; role: string; permissions: string[] };
}

export function hasPermission(permission: string): boolean {
  if (typeof window === "undefined") return false;
  const raw = sessionStorage.getItem("recon_user");
  if (!raw) return false;
  const user = JSON.parse(raw);
  if (user.role === "admin") return true;
  return (user.permissions ?? []).includes(permission);
}

export function logout() {
  sessionStorage.removeItem("recon_token");
  sessionStorage.removeItem("recon_user");
}

export function currentUser(): { name: string; role: string } | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem("recon_user");
  return raw ? JSON.parse(raw) : null;
}

// ── Runs ──────────────────────────────────────────────────────────────────────

export const getRuns = (token?: string) =>
  apiFetch<any[]>("/api/runs/", {}, token);

export const getStats = (token?: string) =>
  apiFetch<any>("/api/runs/stats", {}, token);

export const getRun = (runId: string, token?: string) =>
  apiFetch<any>(`/api/runs/${encodeURIComponent(runId)}`, {}, token);

export const triggerRun = (body: {
  account_ids: string[];
  period: string;
  maker: string;
}) => apiFetch<any>("/api/runs/", { method: "POST", body: JSON.stringify(body) });

// ── Decisions ─────────────────────────────────────────────────────────────────

export const submitDecisions = (body: {
  reviewer: string;
  decisions: Array<{
    account_id: string;
    action: string;
    bank_uids: string[];
    book_uids: string[];
    note?: string;
  }>;
}) => apiFetch<any>("/api/decisions/", { method: "POST", body: JSON.stringify(body) });

// ── Sign-off ──────────────────────────────────────────────────────────────────

export const signOff = (runId: string, body: { checker: string; note?: string }) =>
  apiFetch<any>(`/api/runs/${encodeURIComponent(runId)}/signoff`, {
    method: "POST",
    body: JSON.stringify(body),
  });

// ── Audit ─────────────────────────────────────────────────────────────────────

export const getAudit = (token?: string) =>
  apiFetch<any[]>("/api/audit/", {}, token);

export const verifyChain = () =>
  apiFetch<any>("/api/audit/verify", { method: "POST" });

// ── Accounts ──────────────────────────────────────────────────────────────────

export const getAccounts = (token?: string) =>
  apiFetch<any>("/api/accounts/", {}, token);

// ── Proposed matches ──────────────────────────────────────────────────────────

export const getProposedMatches = (runId: string) =>
  apiFetch<any[]>(`/api/runs/${encodeURIComponent(runId)}/proposed`);

// ── Users (admin) ─────────────────────────────────────────────────────────────

export const getUsers = () => apiFetch<any[]>("/api/users/");

export const getAllPermissions = () =>
  apiFetch<{ permissions: string[] }>("/api/users/permissions/all");

export const createUser = (body: {
  name: string; email: string; password: string;
  is_admin: boolean; permissions: string[];
}) => apiFetch<any>("/api/users/", { method: "POST", body: JSON.stringify(body) });

export const updateUser = (id: number, body: {
  name?: string; is_active?: boolean; permissions?: string[]; password?: string;
}) => apiFetch<any>(`/api/users/${id}`, { method: "PATCH", body: JSON.stringify(body) });

export const deleteUser = (id: number) =>
  apiFetch<void>(`/api/users/${id}`, { method: "DELETE" });

// ── Connectors ────────────────────────────────────────────────────────────────

export const fetchStatement = (body: { account_id: string; period_start: string; period_end: string }) =>
  apiFetch<any>("/api/connectors/statement/fetch", { method: "POST", body: JSON.stringify(body) });

export const fetchLedger = (body: { account_id: string; period_start: string; period_end: string }) =>
  apiFetch<any>("/api/connectors/ledger/fetch", { method: "POST", body: JSON.stringify(body) });

// ── Internal (used by hooks.ts) ───────────────────────────────────────────────

// ── Journals ──────────────────────────────────────────────────────────────────

export const getRunJournals = (runId: string) =>
  apiFetch<any[]>(`/api/runs/${encodeURIComponent(runId)}/journals`);

export const approveJournal = (journalId: number) =>
  apiFetch<any>(`/api/connectors/journals/${journalId}/approve`, { method: "POST" });

// ── Posting ───────────────────────────────────────────────────────────────────

export const getPostingQueue = (runId?: string) =>
  apiFetch<any[]>(`/api/connectors/posting/queue${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`);

export const populatePostingQueue = (runId: string) =>
  apiFetch<any>(`/api/connectors/posting/queue/${encodeURIComponent(runId)}`, { method: "POST" });

export const executePosting = (runId: string) =>
  apiFetch<any>(`/api/connectors/posting/execute/${encodeURIComponent(runId)}`, { method: "POST" });

export const getSchedulerJobs = () =>
  apiFetch<any[]>("/api/connectors/scheduler/jobs");

// ── Internal (used by hooks.ts) ───────────────────────────────────────────────

export async function apiFetchRaw(path: string): Promise<any> {
  return apiFetch<any>(path);
}
