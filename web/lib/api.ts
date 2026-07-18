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

export interface JobLogs {
  logs: string | null;
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
  llm_temperature: number;
  llm_model: string;
  auto_publish_to_ghost: boolean;
}

export interface SettingsUpdate {
  default_tone?: string;
  default_word_count?: number;
  llm_temperature?: number;
  llm_model?: string;
  auto_publish_to_ghost?: boolean;
}

export interface OpenRouterModel {
  id: string;
  name: string;
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
  logs: (id: string) => apiFetch<JobLogs>(`/jobs/${id}/logs`),
  streamEvents: (id: string, handlers: StreamHandlers) => streamJobEvents(id, handlers),
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
  getModels: () => apiFetch<OpenRouterModel[]>('/settings/models'),
};

// ─── SSE event parsing ──────────────────────────────────────────────────────

export interface StreamHandlers {
  onReplay?: (text: string) => void;
  onLine?: (seq: number, line: string) => void;
  onDone?: (status: string) => void;
  onError?: () => void;
}

// Fragment reassembly buffer keyed by seq (module-level is fine: one stream at a time).
const _fragBuffers = new Map<number, string>();

export function parseEvent(data: string, handlers: StreamHandlers): void {
  let obj: Record<string, unknown>;
  try {
    obj = JSON.parse(data);
  } catch {
    return;
  }
  if (typeof obj.replay === 'string') {
    handlers.onReplay?.(obj.replay);
    return;
  }
  if (obj.done) {
    handlers.onDone?.(String(obj.status ?? 'completed'));
    return;
  }
  if (typeof obj.seq === 'number' && typeof obj.line === 'string') {
    if (typeof obj.frag === 'number') {
      const prev = _fragBuffers.get(obj.seq) ?? '';
      const combined = prev + obj.line;
      // The backend explicitly marks the final fragment with `last: true`.
      // A length heuristic is unreliable (UTF-8/emoji-heavy final fragments can
      // legitimately be short without being last, or a non-final fragment could
      // coincidentally be short), so we only flush when `last` is set.
      if (obj.last === true) {
        _fragBuffers.delete(obj.seq);
        handlers.onLine?.(obj.seq, combined);
      } else {
        _fragBuffers.set(obj.seq, combined);
      }
      return;
    }
    handlers.onLine?.(obj.seq, obj.line);
  }
}

export function streamJobEvents(id: string, handlers: StreamHandlers): EventSource {
  const es = new EventSource(`${API}/jobs/${id}/events`, { withCredentials: true });
  es.onmessage = (e) => parseEvent(e.data, handlers);
  es.addEventListener('done', (e) => {
    parseEvent((e as MessageEvent).data, handlers);
    es.close();
  });
  es.onerror = () => handlers.onError?.();
  return es;
}
