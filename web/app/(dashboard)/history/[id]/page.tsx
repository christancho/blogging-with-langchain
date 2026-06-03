'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { jobs, type Job } from '@/lib/api';
import MarkdownRenderer from '@/components/MarkdownRenderer';

export default function PreviewPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    jobs.get(id)
      .then(setJob)
      .catch((err) => { console.error('Failed to load job:', err); router.push('/history'); })
      .finally(() => setLoading(false));
  }, [id, router]);

  async function handlePublish() {
    if (!job) return;
    setError('');
    setPublishing(true);
    try {
      await jobs.publish(job.id);
      router.push('/history');
    } catch (err: unknown) {
      setError((err as Error).message ?? 'Publish failed');
    } finally {
      setPublishing(false);
    }
  }

  async function handleDiscard() {
    if (!job) return;
    setDiscarding(true);
    try {
      await jobs.delete(job.id);
      router.push('/history');
    } catch (err) {
      console.error('Failed to discard job:', err);
    } finally {
      setDiscarding(false);
    }
  }

  if (loading) return <p className="text-gray-400">Loading…</p>;
  if (!job?.result) return <p className="text-gray-500">No preview available.</p>;

  const r = job.result as Record<string, unknown>;
  const title = String(r.seo_title ?? r.title ?? job.topic);
  const metaDescription = String(r.meta_description ?? '');
  const excerpt = String(r.excerpt ?? '');
  const tags = Array.isArray(r.tags) ? (r.tags as string[]).join(', ') : '';
  const wordCount = typeof r.word_count === 'number' ? r.word_count : null;
  const qualityScore = typeof r.quality_score === 'number' ? r.quality_score : null;
  const content = String(r.final_content ?? r.article_content ?? '');

  return (
    <div className="w-full space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Preview</h1>
        <div className="flex gap-3">
          <button
            onClick={handleDiscard}
            disabled={discarding || publishing}
            className="px-4 py-2 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
          >
            {discarding ? 'Discarding…' : 'Discard'}
          </button>
          <button
            onClick={handlePublish}
            disabled={publishing || discarding}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {publishing ? 'Publishing…' : 'Publish to Ghost'}
          </button>
        </div>
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <div className="bg-white shadow rounded-lg p-5 space-y-3">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-0.5">SEO Title</p>
          <p className="font-semibold text-lg">{title}</p>
        </div>
        {metaDescription && (
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-0.5">Meta Description</p>
            <p className="text-sm text-gray-700">{metaDescription}</p>
          </div>
        )}
        {excerpt && (
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-0.5">Excerpt</p>
            <p className="text-sm text-gray-700">{excerpt}</p>
          </div>
        )}
        {tags && (
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-0.5">Tags</p>
            <p className="text-sm text-gray-700">{tags}</p>
          </div>
        )}
        <div className="flex gap-6 text-sm text-gray-500">
          {wordCount && <span>{wordCount.toLocaleString()} words</span>}
          {qualityScore && <span>Quality: {qualityScore}/10</span>}
        </div>
      </div>

      <div className="bg-white shadow rounded-lg p-5">
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-3">Article</p>
        <div>
          <MarkdownRenderer content={content} />
        </div>
      </div>
    </div>
  );
}
