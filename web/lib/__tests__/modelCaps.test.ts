import { capsFor, effectiveModel, rowControls, modelLabel } from '../modelCaps';
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
