import type { OpenRouterModel, NodeLLMSettings } from './api';

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
