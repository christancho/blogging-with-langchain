import { parseJobsSnapshot, subscribeActiveJobs, type Job } from '../api';

const job = (id: string, status: Job['status'] = 'pending'): Job => ({
  id,
  topic: `topic ${id}`,
  tone: 'warm',
  word_count: 100,
  instructions: null,
  session_notes: null,
  status,
  created_at: '2026-10-22T00:00:00+00:00',
  started_at: null,
  completed_at: null,
  current_node: null,
  error: null,
});

describe('parseJobsSnapshot', () => {
  it('parses a JSON array of jobs', () => {
    expect(parseJobsSnapshot(JSON.stringify([job('a'), job('b', 'running')]))).toEqual([
      job('a'),
      job('b', 'running'),
    ]);
  });

  it('returns null for malformed or non-array payloads', () => {
    const err = jest.spyOn(console, 'error').mockImplementation(() => {});
    expect(parseJobsSnapshot('not json')).toBeNull();
    expect(parseJobsSnapshot('{"a":1}')).toBeNull();
    expect(err).toHaveBeenCalledTimes(2);
    err.mockRestore();
  });
});

// Minimal stand-in for the browser EventSource (jest runs in node).
class FakeEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static instances: FakeEventSource[] = [];

  readyState = FakeEventSource.CONNECTING;
  onerror: (() => void) | null = null;
  closed = false;
  private listeners: Record<string, Array<(e: { data: string }) => void>> = {};

  constructor(public url: string, public init?: EventSourceInit) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, fn: (e: { data: string }) => void) {
    (this.listeners[type] ??= []).push(fn);
  }
  close() {
    this.closed = true;
    this.readyState = FakeEventSource.CLOSED;
  }
  emit(type: string, data: string) {
    this.listeners[type]?.forEach((fn) => fn({ data }));
  }
  fail(readyState: number) {
    this.readyState = readyState;
    this.onerror?.();
  }
}

const flush = () => new Promise((r) => setImmediate(r));

describe('subscribeActiveJobs', () => {
  const realFetch = global.fetch;

  beforeEach(() => {
    FakeEventSource.instances = [];
    (global as unknown as { EventSource: unknown }).EventSource = FakeEventSource;
    jest.useFakeTimers({ doNotFake: ['setImmediate'] });
  });

  afterEach(() => {
    jest.useRealTimers();
    global.fetch = realFetch;
  });

  const mockAuthMe = (status: number) => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: status === 200,
      status,
      statusText: String(status),
      json: async () => (status === 200 ? { authenticated: true } : { detail: 'Not authenticated' }),
    }) as unknown as typeof fetch;
  };

  it('opens /jobs/stream with credentials and delivers snapshots', () => {
    const seen: Job[][] = [];
    const stop = subscribeActiveJobs({ onJobs: (j) => seen.push(j), onUnauthorized: () => {} });
    const es = FakeEventSource.instances[0];
    expect(es.url).toBe('/api/proxy/jobs/stream');
    expect(es.init).toEqual({ withCredentials: true });

    es.emit('jobs', JSON.stringify([job('a')]));
    es.emit('jobs', JSON.stringify([]));
    expect(seen).toEqual([[job('a')], []]);
    stop();
    expect(es.closed).toBe(true);
  });

  it('leaves transient drops to the EventSource built-in reconnect', async () => {
    mockAuthMe(200);
    subscribeActiveJobs({ onJobs: () => {}, onUnauthorized: () => {} });
    FakeEventSource.instances[0].fail(FakeEventSource.CONNECTING);
    await flush();
    jest.advanceTimersByTime(10_000);
    expect(global.fetch).not.toHaveBeenCalled();
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it('redirects to login when the stream is rejected and the session is gone', async () => {
    mockAuthMe(401);
    const onUnauthorized = jest.fn();
    subscribeActiveJobs({ onJobs: () => {}, onUnauthorized });
    FakeEventSource.instances[0].fail(FakeEventSource.CLOSED);
    await flush();
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    jest.advanceTimersByTime(10_000);
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it('reopens the stream after a rejection while still logged in', async () => {
    mockAuthMe(200);
    const onUnauthorized = jest.fn();
    subscribeActiveJobs({ onJobs: () => {}, onUnauthorized });
    FakeEventSource.instances[0].fail(FakeEventSource.CLOSED);
    await flush();
    jest.advanceTimersByTime(3000);
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('does not reconnect after unsubscribe', async () => {
    mockAuthMe(200);
    const stop = subscribeActiveJobs({ onJobs: () => {}, onUnauthorized: () => {} });
    FakeEventSource.instances[0].fail(FakeEventSource.CLOSED);
    stop();
    await flush();
    jest.advanceTimersByTime(10_000);
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});
