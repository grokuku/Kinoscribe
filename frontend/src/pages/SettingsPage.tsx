import { useState, useEffect } from 'react';
import { api } from '../api/client';
import type { Setting } from '../types/settings';

export default function SettingsPage() {
  const [settings, setSettings] = useState<Setting[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [ollamaTest, setOllamaTest] = useState<{ ok: boolean; models?: string[]; error?: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      const data = await api.getSettings();
      setSettings(data);
      const map: Record<string, string> = {};
      data.forEach((s) => { map[s.key] = s.value; });
      setForm(map);
    } catch (e: any) {
      alert('Erreur: ' + e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    try {
      const updated = await api.updateSettings(form);
      setSettings(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      alert('Sauvegarde erreur: ' + e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleTestOllama() {
    setTesting(true);
    setOllamaTest(null);
    try {
      // Save URL first so the test uses the latest value
      await api.updateSettings({ ollama_base_url: form.ollama_base_url || '' });
      const result = await api.testOllama();
      setOllamaTest(result);
    } catch (e: any) {
      setOllamaTest({ ok: false, error: e.message });
    } finally {
      setTesting(false);
    }
  }

  const set = (key: string, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  // Group settings by category
  const categories: Record<string, Setting[]> = {};
  for (const s of settings) {
    if (!categories[s.category]) categories[s.category] = [];
    categories[s.category].push(s);
  }

  const categoryLabels: Record<string, string> = {
    llm: '🤖 Serveur LLM (Ollama)',
    translation: '🌐 Traduction',
    subtitles: '📜 Sous-titres',
    external: '🔗 Services externes',
    general: '⚙️ Général',
  };

  if (loading) return <div className="py-16 text-center text-gray-500">Chargement…</div>;

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-100 mb-1">Paramètres</h1>
      <p className="text-sm text-gray-500 mb-8">Configuration de Kinoscribe — tout se gère ici</p>

      {Object.entries(categories).map(([cat, items]) => (
        <div key={cat} className="mb-8">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">
            {categoryLabels[cat] || cat}
          </h2>

          <div className="border border-gray-800 rounded-xl overflow-hidden divide-y divide-gray-800">
            {items.map((s) => (
              <div key={s.key} className="px-4 py-3 flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <label className="block text-sm font-medium text-gray-200">{s.key.replaceAll('_', ' ')}</label>
                  {s.description && (
                    <p className="text-xs text-gray-500 mt-0.5">{s.description}</p>
                  )}
                </div>
                <div className="w-56 flex-shrink-0">
                  {s.input_type === 'select' && s.options ? (
                    <select
                      value={form[s.key] || ''}
                      onChange={(e) => set(s.key, e.target.value)}
                      className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-brand-500"
                    >
                      {s.options.split(',').map((opt) => (
                        <option key={opt} value={opt}>{opt.toUpperCase()}</option>
                      ))}
                    </select>
                  ) : s.input_type === 'password' ? (
                    <input
                      type="password"
                      value={form[s.key] || ''}
                      onChange={(e) => set(s.key, e.target.value)}
                      placeholder="••••••••"
                      className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-brand-500"
                    />
                  ) : (
                    <input
                      type={s.input_type === 'number' ? 'number' : s.input_type === 'url' ? 'url' : 'text'}
                      value={form[s.key] || ''}
                      onChange={(e) => set(s.key, e.target.value)}
                      step={s.input_type === 'number' ? 'any' : undefined}
                      className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-brand-500"
                    />
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Ollama test — right after the LLM section */}
          {cat === 'llm' && (
            <div className="mt-3 flex items-center gap-3">
              <button
                onClick={handleTestOllama}
                disabled={testing}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-600 text-sm text-gray-200 rounded-lg transition-colors disabled:opacity-50"
              >
                {testing ? 'Test en cours…' : '🧪 Tester la connexion'}
              </button>
              {ollamaTest && (
                <div className={`text-sm ${ollamaTest.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                  {ollamaTest.ok ? (
                    <>
                      ✅ Connecté — {ollamaTest.models?.length || 0} modèle(s)
                      {ollamaTest.models && ollamaTest.models.length > 0 && (
                        <span className="text-gray-500 ml-1">
                          ({ollamaTest.models.slice(0, 5).join(', ')}{ollamaTest.models.length > 5 ? '…' : ''})
                        </span>
                      )}
                    </>
                  ) : (
                    <>❌ {ollamaTest.error}</>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      ))}

      {/* Save button */}
      <div className="sticky bottom-4 flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className={`px-6 py-2.5 text-sm font-medium rounded-lg transition-all shadow-lg ${
            saved
              ? 'bg-emerald-600 text-white'
              : 'bg-brand-600 hover:bg-brand-500 text-white disabled:opacity-50'
          }`}
        >
          {saving ? 'Sauvegarde…' : saved ? '✅ Enregistré !' : 'Enregistrer les paramètres'}
        </button>
      </div>
    </div>
  );
}