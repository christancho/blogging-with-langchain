'use client';

import { useState, useEffect, useRef, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { jobs, settings } from '@/lib/api';

const TONE_PRESETS = [
  { name: 'Conversational', value: 'friendly, conversational, and approachable — like a knowledgeable friend explaining something they care about, while remaining authoritative and well-researched' },
  { name: 'Expert Casual', value: 'knowledgeable yet informal — like a senior colleague sharing hard-won insights over coffee, mixing technical depth with relatable language' },
  { name: 'Storyteller', value: 'narrative-driven and engaging — weaving real-world stories and examples throughout, making complex topics feel like compelling reads rather than textbooks' },
  { name: 'Practical', value: 'direct, actionable, and results-focused — every paragraph earns its place by teaching the reader something they can use immediately, with minimal fluff' },
  { name: 'Thought Leader', value: 'bold, opinionated, and forward-looking — taking clear positions on industry trends, challenging conventional wisdom, and backing claims with evidence' },
];

export default function NewPostPage() {
  const router = useRouter();
  const [topic, setTopic] = useState('');
  const [tone, setTone] = useState('');
  const [toneDisplay, setToneDisplay] = useState('');
  const [wordCount, setWordCount] = useState(3500);
  const [instructions, setInstructions] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showToneDropdown, setShowToneDropdown] = useState(false);
  const toneInputRef = useRef<HTMLInputElement>(null);
  const toneDropdownRef = useRef<HTMLDivElement>(null);

  // Pre-fill tone and word count from settings defaults
  useEffect(() => {
    settings.get().then(s => {
      setTone(s.default_tone);
      const matched = TONE_PRESETS.find(p => p.value === s.default_tone);
      setToneDisplay(matched ? matched.name : s.default_tone);
      setWordCount(s.default_word_count);
    }).catch((err) => console.error('Failed to load settings:', err));
  }, []);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        toneDropdownRef.current && !toneDropdownRef.current.contains(e.target as Node) &&
        toneInputRef.current && !toneInputRef.current.contains(e.target as Node)
      ) {
        setShowToneDropdown(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
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
          <div className="relative">
            <input
              ref={toneInputRef}
              type="text"
              value={toneDisplay}
              onChange={e => { setTone(e.target.value); setToneDisplay(e.target.value); setShowToneDropdown(true); }}
              onFocus={() => setShowToneDropdown(true)}
              placeholder="e.g. informative and insightful"
              className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {showToneDropdown && (
              <div
                ref={toneDropdownRef}
                className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg overflow-hidden"
              >
                {TONE_PRESETS.map(preset => (
                  <button
                    key={preset.name}
                    type="button"
                    onClick={() => { setTone(preset.value); setToneDisplay(preset.name); setShowToneDropdown(false); }}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-blue-50 ${tone === preset.value ? 'bg-blue-50 font-medium' : ''}`}
                  >
                    <span className="block text-gray-900 font-medium">{preset.name}</span>
                    <span className="block text-xs text-gray-400">{preset.value}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
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
