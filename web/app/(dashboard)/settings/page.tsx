'use client';

import { useState, useEffect, FormEvent } from 'react';
import { settings } from '@/lib/api';

export default function SettingsPage() {
  const [tone, setTone] = useState('');
  const [wordCount, setWordCount] = useState(3500);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [passwordSaved, setPasswordSaved] = useState(false);
  const [settingsError, setSettingsError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [savingSettings, setSavingSettings] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);

  useEffect(() => {
    settings.get().then(s => {
      setTone(s.default_tone);
      setWordCount(s.default_word_count);
    }).catch((err) => console.error('Failed to load settings:', err));
  }, []);

  async function handleSaveSettings(e: FormEvent) {
    e.preventDefault();
    setSettingsError('');
    setSettingsSaved(false);
    setSavingSettings(true);
    try {
      await settings.update({ default_tone: tone, default_word_count: wordCount });
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

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

  return (
    <div className="max-w-lg space-y-8">
      <h1 className="text-xl font-semibold">Settings</h1>

      {/* Defaults */}
      <div className="bg-white shadow rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Generation Defaults</h2>
        <form onSubmit={handleSaveSettings} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Default tone</label>
            <input
              type="text"
              value={tone}
              onChange={e => setTone(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
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
          API: <span className="font-mono">{apiUrl}</span>
        </p>
        <p className="text-xs text-gray-400 mt-1">
          Ghost, Brave Search, and Anthropic status are managed via environment variables on the API service.
        </p>
      </div>
    </div>
  );
}
