'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { jobs, type Job } from '@/lib/api';

function StatusBadge({ status }: { status: Job['status'] }) {
  const classes: Record<string, string> = {
    pending: 'bg-gray-100 text-gray-700',
    running: 'bg-blue-100 text-blue-700',
    completed: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
    published: 'bg-purple-100 text-purple-700',
  };
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${classes[status] ?? ''}`}>
      {status.toUpperCase()}
    </span>
  );
}

function LogPanel({ jobId }: { jobId: string }) {
  const [logs, setLogs] = useState<string>('');
  const preRef = useRef<HTMLPreElement>(null);
  const userScrolledUp = useRef(false);

  const fetchLogs = useCallback(async () => {
    try {
      const data = await jobs.logs(jobId);
      if (data.logs !== null) setLogs(data.logs);
    } catch (err) {
      console.debug('[LogPanel] log fetch error (best-effort):', err);
    }
  }, [jobId]);

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 2000);
    return () => clearInterval(interval);
  }, [fetchLogs]);

  // Auto-scroll to bottom unless the user has manually scrolled up
  useEffect(() => {
    const el = preRef.current;
    if (!el || userScrolledUp.current) return;
    el.scrollTop = el.scrollHeight;
  }, [logs]);

  function handleScroll() {
    const el = preRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    userScrolledUp.current = !atBottom;
  }

  return (
    <details open className="mt-4">
      <summary className="text-xs font-medium text-gray-500 cursor-pointer select-none uppercase tracking-wide">
        Logs
      </summary>
      <pre
        ref={preRef}
        onScroll={handleScroll}
        className="mt-2 text-xs font-mono bg-gray-950 text-gray-200 rounded p-3 overflow-y-auto max-h-[54rem] whitespace-pre-wrap"
      >
        {logs || 'Waiting for output…'}
      </pre>
    </details>
  );
}

export default function QueuePage() {
  const [allJobs, setAllJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    try {
      const data = await jobs.list();
      setAllJobs(data);
    } catch (err) {
      console.error('Failed to fetch jobs:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 3000);
    return () => clearInterval(interval);
  }, [fetchJobs]);

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await jobs.delete(id);
      setAllJobs(prev => prev.filter(j => j.id !== id));
    } catch (err) {
      console.error('Failed to delete job:', err);
    } finally {
      setDeletingId(null);
    }
  }

  const runningJob = allJobs.find(j => j.status === 'running');
  const pendingJobs = allJobs.filter(j => j.status === 'pending');

  if (loading) {
    return <p className="text-gray-400">Loading…</p>;
  }

  if (!runningJob && pendingJobs.length === 0) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-500 mb-4">Queue is empty.</p>
        <Link href="/new-post" className="text-blue-600 hover:underline">
          Add a topic →
        </Link>
      </div>
    );
  }

  const NODE_LABELS: Record<string, string> = {
    research: 'Researching…',
    audience_analysis: 'Analyzing audience…',
    writer: 'Writing…',
    fact_checker: 'Checking facts…',
    formatter: 'Formatting…',
    seo: 'Optimizing SEO…',
    editor: 'Reviewing…',
    publisher: 'Publishing…',
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Queue</h1>

      {runningJob && (
        <div className="bg-white shadow rounded-lg p-5 border-l-4 border-blue-500">
          <div className="flex items-start justify-between mb-3">
            <div>
              <p className="font-medium">{runningJob.topic}</p>
              <p className="text-sm text-blue-600 mt-0.5">
                {runningJob.current_node
                  ? NODE_LABELS[runningJob.current_node] ?? runningJob.current_node
                  : 'Starting…'}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge status="running" />
              <button
                onClick={() => handleDelete(runningJob.id)}
                disabled={deletingId === runningJob.id}
                className="text-xs text-red-500 hover:text-red-700 disabled:opacity-50"
              >
                {deletingId === runningJob.id ? 'Removing…' : 'Remove'}
              </button>
            </div>
          </div>
          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full bg-blue-500 rounded-full animate-[pulse_1.5s_ease-in-out_infinite] w-1/2" />
          </div>
          <LogPanel jobId={runningJob.id} />
        </div>
      )}

      {pendingJobs.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-gray-500 font-medium uppercase tracking-wide">
            Pending ({pendingJobs.length})
          </p>
          {pendingJobs.map(job => (
            <div
              key={job.id}
              className="bg-white shadow rounded-lg px-4 py-3 flex items-center justify-between"
            >
              <span className="text-sm">{job.topic}</span>
              <button
                onClick={() => handleDelete(job.id)}
                disabled={deletingId === job.id}
                className="text-xs text-red-500 hover:text-red-700 disabled:opacity-50 ml-4"
              >
                {deletingId === job.id ? 'Removing…' : 'Remove'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
