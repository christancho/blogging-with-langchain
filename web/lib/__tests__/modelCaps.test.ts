import { capsFor, effectiveModel, rowControls, modelLabel, rowCaps, autoConfigErrors } from '../modelCaps';
import type { OpenRouterModel, NodeLLMSettings } from '../api';

const models = [
  { id: 'a/think', name: 'Think', supports_reasoning: true, supports_temperature: true },
  { id: 'a/plain', name: 'Plain', supports_reasoning: false, supports_temperature: true },
] as OpenRouterModel[];

test('capsFor unknown id is null', () => expect(capsFor(models, 'a/gone')).toBeNull());
test('modelLabel falls back to raw id', () => {
  expect(modelLabel(models, 'a/think')).toBe('Think');
  expect(modelLabel(models, 'a/gone')).toBe('a/gone');
});
test('effectiveModel prefers node override', () => {
  expect(effectiveModel({ effort: 'high', temperature: 0.7, model: 'a/plain' }, 'a/think')).toBe('a/plain');
  expect(effectiveModel({ effort: 'high', temperature: 0.7 }, 'a/think')).toBe('a/think');
});
test('rowControls disables effort for a non-reasoning override', () => {
  const s = { effort: 'high', temperature: 0.7, model: 'a/plain' } as NodeLLMSettings;
  expect(rowControls(capsFor(models, 'a/plain'), s)).toEqual({ effortEnabled: false, temperatureEnabled: true });
  expect(rowControls(capsFor(models, 'a/think'), s)).toEqual({ effortEnabled: true, temperatureEnabled: false });
});
test('rowControls with unknown caps follows effort', () => {
  expect(rowControls(null, { effort: 'off', temperature: 0.7 })).toEqual({ effortEnabled: true, temperatureEnabled: true });
});

const auto = (pool: string[]) => ({ effort: 'high', temperature: 0.7, model: 'auto',
  auto: { pool: pool.map(m => ({ model: m, criteria: 'c' })), fallback: pool[0] } }) as NodeLLMSettings;

test('rowCaps intersects pool capabilities', () =>
  expect(rowCaps(models, auto(['a/think', 'a/plain']), 'a/think')).toEqual({ reasoning: false, temperature: true }));
test('rowCaps unknown pool model is null', () =>
  expect(rowCaps(models, auto(['a/think', 'a/gone']), 'a/think')).toBeNull());
test('rowCaps fixed row uses effective model', () =>
  expect(rowCaps(models, { effort: 'high', temperature: 0.7 }, 'a/plain')).toEqual({ reasoning: false, temperature: true }));
test('autoConfigErrors', () => {
  expect(autoConfigErrors(auto(['a/think', 'a/plain']).auto)).toEqual([]);
  expect(autoConfigErrors(auto(['a/think']).auto)).toContain('Pick 2–5 models');
  expect(autoConfigErrors(auto(['a/think', 'a/think']).auto)).toContain('Models must be different');
  expect(autoConfigErrors({ pool: [{ model: 'a/think', criteria: ' ' }, { model: 'a/plain', criteria: 'c' }], fallback: 'a/think' }))
    .toContain('Each model needs criteria');
  expect(autoConfigErrors({ ...auto(['a/think', 'a/plain']).auto!, fallback: '' })).toContain('Pick a fallback model');
  expect(autoConfigErrors({ ...auto(['a/think', 'a/plain']).auto!, min_confidence: 2 })).toContain('Min confidence must be between 0 and 1');
});
