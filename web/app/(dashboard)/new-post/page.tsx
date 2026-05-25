'use client';

import { useState, useEffect, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { jobs, settings } from '@/lib/api';

export default function NewPostPage() {
  const router = useRouter();
  const [topic, setTopic] = useState('');
  const [tone, setTone] = useState('');
  const [wordCount, setWordCount] = useState(3500);
  const [instructions, setInstructions] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Pre-fill tone and word count from settings defaults
  useEffect(() => {
    settings.get().then(s => {
      setTone(s.default_tone);
      setWordCount(s.default_word_count);
    }).catch((err) => console.error('Failed to load settings:', err));
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await jobs.create({
        topic,
        tone: tone || undefined,
        word_count: wordCount || undefined,
        instructions: instructions || undefined,
      });
      router.push('/queue');
    } catch {
      setError('Failed to create job. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-lg">
      <h1 className="text-xl font-semibold mb-6">New Post</h1>
      <form onSubmit={handleSubmit} className="bg-white shadow rounded-lg p-6 space-y-5">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Topic <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={topic}
            onChange={e => setTopic(e.target.value)}
            required
            placeholder="e.g. Building RAG systems with LangChain"
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Tone</label>
          <input
            type="text"
            value={tone}
            onChange={e => setTone(e.target.value)}
            placeholder="e.g. informative and insightful"
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Target word count
          </label>
          <input
            type="number"
            value={wordCount}
            onChange={e => setWordCount(Number(e.target.value))}
            min={500}
            max={10000}
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Custom instructions <span className="text-gray-400 font-normal">(optional)</span>
          </label>
          <textarea
            value={instructions}
            onChange={e => setInstructions(e.target.value)}
            rows={3}
            placeholder="e.g. Focus on practical examples for Python developers"
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          />
        </div>
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 text-white py-2 rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Adding to queue…' : 'Add to queue'}
        </button>
      </form>
    </div>
  );
}
