import type { OpenRouterModel, NodeLLMSettings, AutoConfig } from './api';

/** Model value that routes a step through JEV. */
export const AUTO_MODEL = 'auto';

export type Caps = { reasoning: boolean; temperature: boolean } | null;

/**
 * Look up a model's capabilities.
 *
 * @param models - Models returned by /settings/models.
 * @param id - OpenRouter model id.
 * @returns Capability flags, or null when the id is not in the list.
 */
export function capsFor(models: OpenRouterModel[], id: string): Caps {
  const m = models.find(x => x.id === id);
  return m ? { reasoning: m.supports_reasoning, temperature: m.supports_temperature } : null;
}

/**
 * Model a step actually runs on: its override, else the default model.
 *
 * @param s - The step's settings.
 * @param defaultModel - The default model id.
 * @returns The effective model id.
 */
export function effectiveModel(s: NodeLLMSettings, defaultModel: string): string {
  return s.model ?? defaultModel;
}

/**
 * Which effort/temperature inputs are enabled for a step. Mirrors
 * Config.get_llm(): unknown capabilities fall back to "effort unless off,
 * then temperature".
 *
 * @param caps - Capabilities of the step's effective model (null if unknown).
 * @param s - The step's settings.
 * @returns Enabled flags for the two inputs.
 */
export function rowControls(
  caps: Caps,
  s: NodeLLMSettings,
): { effortEnabled: boolean; temperatureEnabled: boolean } {
  const effortEnabled = caps ? caps.reasoning : true;
  let temperatureEnabled: boolean;
  if (!caps) temperatureEnabled = s.effort === 'off';
  else if (!caps.temperature) temperatureEnabled = false;
  else temperatureEnabled = !caps.reasoning || s.effort === 'off';
  return { effortEnabled, temperatureEnabled };
}

/**
 * Display name for a model id.
 *
 * @param models - Models returned by /settings/models.
 * @param id - OpenRouter model id.
 * @returns The model's name, or the raw id when it is not listed.
 */
export function modelLabel(models: OpenRouterModel[], id: string): string {
  return models.find(m => m.id === id)?.name ?? id;
}

/**
 * Capabilities that apply to a step's row. For an Auto row, the AND of every
 * pool model's capabilities (any one of them may run); otherwise the
 * effective model's.
 *
 * @param models - Models returned by /settings/models.
 * @param s - The step's settings.
 * @param defaultModel - The default model id.
 * @returns Capability flags, or null when unknown (empty pool, or a pool model not listed).
 */
export function rowCaps(models: OpenRouterModel[], s: NodeLLMSettings, defaultModel: string): Caps {
  if (s.model !== AUTO_MODEL) return capsFor(models, effectiveModel(s, defaultModel));
  const pool = s.auto?.pool ?? [];
  if (pool.length === 0) return null;
  let reasoning = true;
  let temperature = true;
  for (const entry of pool) {
    const c = capsFor(models, entry.model);
    if (!c) return null;
    reasoning = reasoning && c.reasoning;
    temperature = temperature && c.temperature;
  }
  return { reasoning, temperature };
}

/**
 * User-facing validation errors for an Auto config; mirrors the server rules
 * in Config._validate_auto_block.
 *
 * @param auto - The step's Auto config (undefined when absent).
 * @returns Error messages; empty when the config is valid.
 */
export function autoConfigErrors(auto: AutoConfig | undefined): string[] {
  if (!auto) return ['Pick 2–5 models'];
  const errors: string[] = [];
  const pool = auto.pool;
  if (pool.length < 2 || pool.length > 5 || pool.some(e => !e.model)) errors.push('Pick 2–5 models');
  if (new Set(pool.map(e => e.model)).size !== pool.length) errors.push('Models must be different');
  if (pool.some(e => !e.criteria.trim())) errors.push('Each model needs criteria');
  if (!auto.fallback) errors.push('Pick a fallback model');
  const mc = auto.min_confidence;
  if (mc !== undefined && !(mc >= 0 && mc <= 1)) errors.push('Min confidence must be between 0 and 1');
  return errors;
}
