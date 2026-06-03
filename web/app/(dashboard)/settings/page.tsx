'use client';

import { useState, useEffect, useRef, FormEvent } from 'react';
import { settings, OpenRouterModel } from '@/lib/api';

const TONE_PRESETS = [
  { name: 'Conversational', value: 'friendly, conversational, and approachable — like a knowledgeable friend explaining something they care about, while remaining authoritative and well-researched' },
  { name: 'Expert Casual', value: 'knowledgeable yet informal — like a senior colleague sharing hard-won insights over coffee, mixing technical depth with relatable language' },
  { name: 'Storyteller', value: 'narrative-driven and engaging — weaving real-world stories and examples throughout, making complex topics feel like compelling reads rather than textbooks' },
  { name: 'Practical', value: 'direct, actionable, and results-focused — every paragraph earns its place by teaching the reader something they can use immediately, with minimal fluff' },
  { name: 'Thought Leader', value: 'bold, opinionated, and forward-looking — taking clear positions on industry trends, challenging conventional wisdom, and backing claims with evidence' },
];

export default function SettingsPage() {
  const [tone, setTone] = useState('');
  const [toneDisplay, setToneDisplay] = useState('');
  const [wordCount, setWordCount] = useState(3500);
  const [llmTemperature, setLlmTemperature] = useState(0.7);
  const [llmModel, setLlmModel] = useState('');
  const [models, setModels] = useState<OpenRouterModel[]>([]);
  const [modelSearch, setModelSearch] = useState('');
  const [showModelDropdown, setShowModelDropdown] = useState(false);
  const [modelsLoading, setModelsLoading] = useState(true);
  const modelInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const [showToneDropdown, setShowToneDropdown] = useState(false);
  const toneInputRef = useRef<HTMLInputElement>(null);
  const toneDropdownRef = useRef<HTMLDivElement>(null);

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [passwordSaved, setPasswordSaved] = useState(false);
  const [settingsError, setSettingsError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [savingSettings, setSavingSettings] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);
  const [settingsLoadError, setSettingsLoadError] = useState('');

  useEffect(() => {
    settings.get().then(s => {
      setTone(s.default_tone);
      const matched = TONE_PRESETS.find(p => p.value === s.default_tone);
      setToneDisplay(matched ? matched.name : s.default_tone);
      setWordCount(s.default_word_count);
      setLlmTemperature(s.llm_temperature);
      setLlmModel(s.llm_model);
    }).catch((err) => {
      console.error('Failed to load settings:', err);
      setSettingsLoadError('Failed to load settings. Please refresh the page.');
    });

    settings.getModels().then(ms => {
      setModels(ms);
    }).catch((err) => console.error('Failed to load models:', err))
      .finally(() => setModelsLoading(false));
  }, []);

  // Close dropdowns when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
        modelInputRef.current && !modelInputRef.current.contains(e.target as Node)
      ) {
        setShowModelDropdown(false);
        const selected = models.find(m => m.id === llmModel);
        setModelSearch(selected ? selected.name : llmModel);
      }
      if (
        toneDropdownRef.current && !toneDropdownRef.current.contains(e.target as Node) &&
        toneInputRef.current && !toneInputRef.current.contains(e.target as Node)
      ) {
        setShowToneDropdown(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [llmModel, models]);

  const filteredModels = models.filter(m =>
    m.name.toLowerCase().includes(modelSearch.toLowerCase()) ||
    m.id.toLowerCase().includes(modelSearch.toLowerCase())
  );

  // Once models are loaded, resolve the current model's display name
  useEffect(() => {
    if (models.length > 0 && llmModel) {
      const selected = models.find(m => m.id === llmModel);
      if (selected) setModelSearch(selected.name);
    }
  }, [models, llmModel]);

  function selectModel(model: OpenRouterModel) {
    setLlmModel(model.id);
    setModelSearch(model.name);
    setShowModelDropdown(false);
  }

  async function handleSaveSettings(e: FormEvent) {
    e.preventDefault();
    setSettingsError('');
    setSettingsSaved(false);
    if (!llmModel) {
      setSettingsError('Please select a model before saving.');
      return;
    }
    setSavingSettings(true);
    try {
      await settings.update({
        default_tone: tone,
        default_word_count: wordCount,
        llm_temperature: llmTemperature,
        llm_model: llmModel,
      });
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 2000);
    } catch (err) {
      console.error('Failed to save settings:', err);
      setSettingsError('Failed to save settings.');
    } finally {
      setSavingSettings(false);
    }
  }

  async function handleChangePassword(e: FormEvent) {
    e.preventDefault();
    setPasswordError('');
    setPasswordSaved(false);
    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match.');
      return;
    }
    setSavingPassword(true);
    try {
      await settings.changePassword({ new_password: newPassword, confirm_password: confirmPassword });
      setPasswordSaved(true);
      setNewPassword('');
      setConfirmPassword('');
      setTimeout(() => setPasswordSaved(false), 2000);
    } catch (err) {
      console.error('Failed to change password:', err);
      setPasswordError('Failed to change password.');
    } finally {
      setSavingPassword(false);
    }
  }

  return (
    <div className="max-w-lg space-y-8">
      <h1 className="text-xl font-semibold">Settings</h1>

      {settingsLoadError && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
          {settingsLoadError}
        </div>
      )}

      {/* Defaults */}
      <div className="bg-white shadow rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Generation Defaults</h2>
        <form onSubmit={handleSaveSettings} className="space-y-4">

          {/* Model selector */}
          <div>
            <label htmlFor="llm-model" className="block text-sm font-medium text-gray-700 mb-1">Model</label>
            <div className="relative">
              <input
                id="llm-model"
                ref={modelInputRef}
                type="text"
                value={modelSearch}
                onChange={e => { setModelSearch(e.target.value); setShowModelDropdown(true); }}
                onFocus={() => setShowModelDropdown(true)}
                placeholder={modelsLoading ? 'Loading models…' : 'Search models…'}
                disabled={modelsLoading}
                className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
              />
              {showModelDropdown && (
                <div
                  ref={dropdownRef}
                  className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-y-auto"
                >
                  {filteredModels.length === 0 ? (
                    <p className="px-3 py-2 text-sm text-gray-400">No models match your search.</p>
                  ) : (
                    filteredModels.map(m => (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => selectModel(m)}
                        className={`w-full text-left px-3 py-2 text-sm hover:bg-blue-50 ${m.id === llmModel ? 'bg-blue-50 font-medium' : ''}`}
                      >
                        <span className="block text-gray-900">{m.name}</span>
                        <span className="block text-xs text-gray-400 font-mono">{m.id}</span>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Temperature */}
          <div>
            <label htmlFor="llm-temperature" className="block text-sm font-medium text-gray-700 mb-1">
              Temperature
              <span className="ml-2 font-normal text-gray-500">{llmTemperature.toFixed(2)}</span>
            </label>
            <input
              id="llm-temperature"
              type="range"
              min={0}
              max={2}
              step={0.05}
              value={llmTemperature}
              onChange={e => setLlmTemperature(Number(e.target.value))}
              className="w-full accent-blue-600"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-0.5">
              <span>0 — deterministic</span>
              <span>2 — most creative</span>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              Controls randomness. Values above 1.0 may not be supported by all models.
            </p>
          </div>

          {/* Tone */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Default tone</label>
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

          {/* Word count */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Default word count</label>
            <input
              type="number"
              value={wordCount}
              onChange={e => setWordCount(Number(e.target.value))}
              min={500}
              max={10000}
              className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {settingsError && <p className="text-red-600 text-sm">{settingsError}</p>}
          <button
            type="submit"
            disabled={savingSettings}
            className="px-4 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {settingsSaved ? '✓ Saved' : savingSettings ? 'Saving…' : 'Save'}
          </button>
        </form>
      </div>

      {/* Change password */}
      <div className="bg-white shadow rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Change Password</h2>
        <form onSubmit={handleChangePassword} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">New password</label>
            <input
              type="password"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              required
              className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Confirm password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              required
              className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          {passwordError && <p className="text-red-600 text-sm">{passwordError}</p>}
          <button
            type="submit"
            disabled={savingPassword}
            className="px-4 py-2 bg-gray-800 text-white text-sm rounded-md hover:bg-gray-900 disabled:opacity-50"
          >
            {passwordSaved ? '✓ Changed' : savingPassword ? 'Saving…' : 'Change password'}
          </button>
        </form>
      </div>

      {/* Integration status */}
      <div className="bg-white shadow rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Integration Status</h2>
        <p className="text-xs text-gray-400">
          API: <span className="font-mono">/api/proxy</span>
        </p>
        <p className="text-xs text-gray-400 mt-1">
          Ghost, Brave Search, and OpenRouter credentials are managed via environment variables on the API service.
        </p>
      </div>
    </div>
  );
}
