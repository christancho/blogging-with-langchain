'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { jobs, type Job } from '@/lib/api';

function HistoryBadge({ status }: { status: Job['status'] }) {
  if (status === 'completed') {
    return (
      <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-800">
        READY TO REVIEW
      </span>
    );
  }
  if (status === 'published') {
    return (
      <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-700">
        PUBLISHED
      </span>
    );
  }
  if (status === 'failed') {
    return (
      <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-red-100 text-red-700">
        FAILED
      </span>
    );
  }
  return null;
}

export default function HistoryPage() {
  const router = useRouter();
  const [allJobs, setAllJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [dismissingId, setDismissingId] = useState<string | null>(null);

  useEffect(() => {
    jobs.list()
      .then(data => setAllJobs(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function handleRetry(id: string) {
    setRetryingId(id);
    try {
      const newJob = await jobs.retry(id);
      setAllJobs(prev => prev.map(j => j.id === id ? { ...j, status: 'failed' as const } : j));
      router.push('/queue');
      // Add new pending job to list
      setAllJobs(prev => [newJob, ...prev]);
    } catch {
      // ignore
    } finally {
      setRetryingId(null);
    }
  }

  async function handleDismiss(id: string) {
    setDismissingId(id);
    try {
      await jobs.delete(id);
      setAllJobs(prev => prev.filter(j => j.id !== id));
    } catch {
      // ignore
    } finally {
      setDismissingId(null);
    }
  }

  const historyJobs = allJobs.filter(
    j => j.status === 'completed' || j.status === 'published' || j.status === 'failed'
  );

  if (loading) return <p className="text-gray-400">Loading…</p>;

  if (historyJobs.length === 0) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-500">No completed posts yet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">History</h1>
      {historyJobs.map(job => (
        <div key={job.id} className="bg-white shadow rounded-lg p-4 space-y-2">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <p className="font-medium truncate">{job.topic}</p>
              <p className="text-xs text-gray-400 mt-0.5">
                {new Date(job.created_at).toLocaleDateString('en-CA', {
                  year: 'numeric', month: 'short', day: 'numeric',
                })}
              </p>
            </div>
            <HistoryBadge status={job.status} />
          </div>

          {job.status === 'completed' && (
            <button
              onClick={() => router.push(`/history/${job.id}`)}
              className="text-sm text-blue-600 hover:underline"
            >
              Preview &amp; Publish →
            </button>
          )}

          {job.status === 'published' && job.result && (
            <a
              href={(job.result as Record<string, string>).ghost_post_url ?? '#'}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-green-600 hover:underline"
            >
              View on Ghost →
            </a>
          )}

          {job.status === 'failed' && (
            <div className="space-y-1">
              {job.error && (
                <p className="text-xs text-red-600 font-mono truncate">{job.error}</p>
              )}
              <div className="flex gap-3">
                <button
                  onClick={() => handleRetry(job.id)}
                  disabled={retryingId === job.id}
                  className="text-sm text-blue-600 hover:underline disabled:opacity-50"
                >
                  {retryingId === job.id ? 'Retrying…' : 'Retry'}
                </button>
                <button
                  onClick={() => handleDismiss(job.id)}
                  disabled={dismissingId === job.id}
                  className="text-sm text-gray-500 hover:text-gray-700 disabled:opacity-50"
                >
                  {dismissingId === job.id ? 'Dismissing…' : 'Dismiss'}
                </button>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
