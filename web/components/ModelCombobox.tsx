'use client';

import { useState, useEffect, useRef } from 'react';
import type { OpenRouterModel } from '@/lib/api';

interface ModelComboboxProps {
  id: string;
  ariaLabel: string;
  value: string | null;
  onChange: (id: string | null) => void;
  models: OpenRouterModel[];
  loading: boolean;
  defaultLabel?: string;
}

/**
 * Searchable OpenRouter model picker.
 *
 * When `defaultLabel` is set, the first option is that label and maps to
 * `null`; a `null` value displays `defaultLabel`.
 *
 * @param props - See ModelComboboxProps.
 * @returns The combobox element.
 */
export default function ModelCombobox({
  id, ariaLabel, value, onChange, models, loading, defaultLabel,
}: ModelComboboxProps) {
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const displayFor = (v: string | null): string => {
    if (v === null) return defaultLabel ?? '';
    return models.find(m => m.id === v)?.name ?? v;
  };

  // Keep the text in sync with the value (and resolve names once models load)
  // unless the user is searching.
  useEffect(() => {
    if (!open) setSearch(displayFor(value));
  }, [value, models, defaultLabel, open]);

  // Close the dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
        inputRef.current && !inputRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const query = search.toLowerCase();
  const filtered = models.filter(m =>
    m.name.toLowerCase().includes(query) || m.id.toLowerCase().includes(query)
  );

  function select(next: string | null) {
    onChange(next);
    setSearch(displayFor(next));
    setOpen(false);
  }

  return (
    <div className="relative">
      <input
        id={id}
        aria-label={ariaLabel}
        ref={inputRef}
        type="text"
        value={search}
        onChange={e => { setSearch(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder={loading ? 'Loading models…' : 'Search models…'}
        disabled={loading}
        className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
      />
      {open && (
        <div
          ref={dropdownRef}
          className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-y-auto"
        >
          {defaultLabel && (
            <button
              type="button"
              onClick={() => select(null)}
              className={`w-full text-left px-3 py-2 text-sm hover:bg-blue-50 ${value === null ? 'bg-blue-50 font-medium' : ''}`}
            >
              <span className="block text-gray-900">{defaultLabel}</span>
            </button>
          )}
          {filtered.length === 0 ? (
            <p className="px-3 py-2 text-sm text-gray-400">No models match your search.</p>
          ) : (
            filtered.map(m => (
              <button
                key={m.id}
                type="button"
                onClick={() => select(m.id)}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-blue-50 ${m.id === value ? 'bg-blue-50 font-medium' : ''}`}
              >
                <span className="block text-gray-900">{m.name}</span>
                <span className="block text-xs text-gray-400 font-mono">{m.id}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
