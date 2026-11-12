'use client';

import type { AutoConfig, OpenRouterModel } from '@/lib/api';
import ModelCombobox from '@/components/ModelCombobox';

const MAX_POOL = 5;

interface AutoPoolEditorProps {
  node: string;
  value: AutoConfig;
  onChange: (a: AutoConfig) => void;
  models: OpenRouterModel[];
  loading: boolean;
}

/**
 * Editor for a step's Auto (JEV) config: the candidate model pool with
 * per-model criteria, the fallback model, and the minimum confidence.
 *
 * @param props - See AutoPoolEditorProps.
 * @returns A full-width table row; render it inside the settings table body.
 */
export default function AutoPoolEditor({ node, value, onChange, models, loading }: AutoPoolEditorProps) {
  const setEntry = (i: number, patch: Partial<AutoConfig['pool'][number]>) =>
    onChange({ ...value, pool: value.pool.map((e, j) => (j === i ? { ...e, ...patch } : e)) });

  return (
    <tr>
      <td colSpan={4} className="pb-3">
        <div className="ml-2 pl-3 border-l-2 border-blue-200 space-y-3">
          <p className="text-xs text-gray-500">
            Pick 2–5 models and describe when each one fits; JEV chooses per job from the criteria.
          </p>
          {value.pool.map((entry, i) => (
            <div key={i} className="grid grid-cols-[1fr_2fr_auto] gap-2 items-start">
              <ModelCombobox
                id={`auto-${node}-model-${i}`}
                ariaLabel={`${node} pool model ${i + 1}`}
                value={entry.model || null}
                onChange={m => setEntry(i, { model: m ?? '' })}
                models={models}
                loading={loading}
              />
              <textarea
                aria-label={`${node} pool criteria ${i + 1}`}
                value={entry.criteria}
                onChange={e => setEntry(i, { criteria: e.target.value })}
                placeholder="When should this model be used?"
                rows={2}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="button"
                onClick={() => onChange({ ...value, pool: value.pool.filter((_, j) => j !== i) })}
                className="px-2 py-2 text-xs text-gray-500 hover:text-red-600"
              >
                Remove
              </button>
            </div>
          ))}
          <button
            type="button"
            disabled={value.pool.length >= MAX_POOL}
            onClick={() => onChange({ ...value, pool: [...value.pool, { model: '', criteria: '' }] })}
            className="text-xs text-blue-600 hover:text-blue-800 disabled:text-gray-300"
          >
            + Add model
          </button>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label htmlFor={`auto-${node}-fallback`} className="block text-xs text-gray-500 mb-1">Fallback model</label>
              <ModelCombobox
                id={`auto-${node}-fallback`}
                ariaLabel={`${node} fallback model`}
                value={value.fallback || null}
                onChange={m => onChange({ ...value, fallback: m ?? '' })}
                models={models}
                loading={loading}
              />
            </div>
            <div>
              <label htmlFor={`auto-${node}-minconf`} className="block text-xs text-gray-500 mb-1">Min confidence</label>
              <input
                id={`auto-${node}-minconf`}
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={value.min_confidence ?? ''}
                onChange={e => onChange({
                  ...value,
                  min_confidence: e.target.value === '' ? undefined : Number(e.target.value),
                })}
                className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}
