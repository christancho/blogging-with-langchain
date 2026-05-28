const API = '/api/proxy';

// ─── Types ────────────────────────────────────────────────────────────────────

export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'published';

export interface Job {
  id: string;
  topic: string;
  tone: string;
  word_count: number;
  instructions: string | null;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  current_node: string | null;
  error: string | null;
  result?: Record<string, unknown> | null;
}

export interface JobCreate {
  topic: string;
  tone?: string;
  word_count?: number;
  instructions?: string;
}

export interface Settings {
  default_tone: string;
  default_word_count: number;
}

export interface SettingsUpdate {
  default_tone?: string;
  default_word_count?: number;
}

export interface PasswordChange {
  new_password: string;
  confirm_password: string;
}

// ─── Internal fetch helper ────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw Object.assign(new Error(body.detail ?? res.statusText), { status: res.status });
  }
  // 204 No Content — return empty object
  if (res.status === 204) return {} as T;
  return res.json();
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const auth = {
  login: (password: string) =>
    apiFetch<{ ok: boolean }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  logout: () => apiFetch<{ ok: boolean }>('/auth/logout', { method: 'POST' }),
  me: () => apiFetch<{ authenticated: boolean }>('/auth/me'),
};

// ─── Jobs ─────────────────────────────────────────────────────────────────────

export const jobs = {
  list: () => apiFetch<Job[]>('/jobs'),
  get: (id: string) => apiFetch<Job>(`/jobs/${id}`),
  create: (body: JobCreate) =>
    apiFetch<Job>('/jobs', { method: 'POST', body: JSON.stringify(body) }),
  delete: (id: string) => apiFetch<{}>(`/jobs/${id}`, { method: 'DELETE' }),
  publish: (id: string) =>
    apiFetch<{ url: string; post_id: string }>(`/jobs/${id}/publish`, { method: 'POST' }),
  retry: (id: string) => apiFetch<Job>(`/jobs/${id}/retry`, { method: 'POST' }),
};

// ─── Settings ─────────────────────────────────────────────────────────────────

export const settings = {
  get: () => apiFetch<Settings>('/settings'),
  update: (body: SettingsUpdate) =>
    apiFetch<Settings>('/settings', { method: 'PUT', body: JSON.stringify(body) }),
  changePassword: (body: PasswordChange) =>
    apiFetch<{ ok: boolean }>('/settings/password', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
};
