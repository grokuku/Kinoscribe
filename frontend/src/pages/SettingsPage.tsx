import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import type { Setting } from '../types/settings';
import { Save, CheckCircle2, Wifi, WifiOff, RefreshCw, Cpu, Box, X } from 'lucide-react';

// ─── Toast system (simplified) ──────────────────────────────────────────
type ToastType = 'success' | 'error' | 'info';
interface ToastMsg { id: number; type: ToastType; message: string; }
let _tid = 0;
const _tls = new Set<(t: ToastMsg[]) => void>();
let _ts: ToastMsg[] = [];
function _push(type: ToastType, message: string) {
  const id = ++_tid;
  _ts = [..._ts, { id, type, message }];
  _tls.forEach(l => l([..._ts]));
  setTimeout(() => { _ts = _ts.filter(x => x.id !== id); _tls.forEach(l => l([..._ts])); }, 4000);
}
function _useToasts() {
  const [t, setT] = useState<ToastMsg[]>(_ts);
  useEffect(() => { _tls.add(setT); return () => { _tls.delete(setT); }; }, []);
  return t;
}
const toast = { success: (m: string) => _push('success', m), error: (m: string) => _push('error', m), info: (m: string) => _push('info', m) };
function _ToastBar() {
  const toasts = _useToasts();
  if (!toasts.length) return null;
  return <div className="fixed top-4 right-4 z-[100] space-y-2 max-w-sm">{toasts.map(t => (
    <div key={t.id} className={`flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium ${t.type === 'error' ? 'bg-red-500/90 text-white' : t.type === 'success' ? 'bg-emerald-500/90 text-white' : 'bg-brand-500/90 text-white'}`}>
      <span className="flex-1">{t.message}</span>
      <button onClick={() => { _ts = _ts.filter(x => x.id !== t.id); _tls.forEach(l => l([..._ts])); }} className="opacity-70 hover:opacity-100"><X className="w-3.5 h-3.5" /></button>
    </div>))}</div>;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Setting[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [ollamaTest, setOllamaTest] = useState<{ ok: boolean; models?: string[]; error?: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});

  // Dynamic Ollama models list
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const data = await api.getSettings();
      setSettings(data);
      const map: Record<string, string> = {};
      data.forEach((s) => { map[s.key] = s.value; });
      setForm(map);
      if (map.ollama_base_url) fetchModels(map.ollama_base_url);
    } catch (e: any) {
      toast.error('Erreur : ' + e.message);
    } finally {
      setLoading(false);
    }
  }

  async function fetchModels(baseUrl: string) {
    if (!baseUrl.trim()) { setOllamaModels([]); return; }
    setFetchingModels(true);
    setModelsError(null);
    try {
      const result = await api.fetchOllamaModels(baseUrl);
      if (result.ok) setOllamaModels(result.models);
      else { setOllamaModels([]); setModelsError(result.error || 'Erreur inconnue'); }
    } catch (e: any) { setOllamaModels([]); setModelsError(e.message); }
    finally { setFetchingModels(false); }
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
      toast.error('Sauvegarde : ' + e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleTestOllama() {
    setTesting(true);
    setOllamaTest(null);
    try {
      await api.updateSettings({ ollama_base_url: form.ollama_base_url || '' });
      const result = await api.testOllama();
      setOllamaTest(result);
      if (result.ok && result.models) setOllamaModels(result.models);
    } catch (e: any) {
      setOllamaTest({ ok: false, error: e.message });
    } finally {
      setTesting(false);
    }
  }

  const set = (key: string, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  // Group settings by category (hide deprecated ones)
  const hiddenKeys = new Set(['default_source_language']);
  const categories: Record<string, Setting[]> = {};
  for (const s of settings) {
    if (hiddenKeys.has(s.key)) continue;
    if (!categories[s.category]) categories[s.category] = [];
    categories[s.category].push(s);
  }

  const categoryConfig: Record<string, { label: string; icon: typeof Cpu; description: string }> = {
    llm: {
      label: 'Serveur LLM (Ollama)',
      icon: Cpu,
      description: 'Configuration du modèle de langage et du serveur Ollama',
    },
    translation: {
      label: 'Traduction',
      icon: Box,
      description: 'Paramètres du moteur de traduction',
    },
    subtitles: {
      label: 'Sous-titres',
      icon: Box,
      description: 'Traitement et formatage des sous-titres',
    },
    external: {
      label: 'Services externes',
      icon: Box,
      description: 'API et intégrations tierces',
    },
    general: {
      label: 'Général',
      icon: Box,
      description: 'Paramètres généraux',
    },
  };

  const modelKeys = new Set(['ollama_model', 'ollama_refine_model']);

  const handleUrlChange = useCallback(
    (() => {
      let timeout: ReturnType<typeof setTimeout>;
      return (value: string) => {
        set('ollama_base_url', value);
        clearTimeout(timeout);
        timeout = setTimeout(() => fetchModels(value), 800);
      };
    })(),
    []
  );

  // Pretty label from key
  const prettyLabel = (key: string) => {
    const map: Record<string, string> = {
      ollama_base_url: 'URL du serveur',
      ollama_model: 'Modèle de draft',
      ollama_refine_model: "Modèle d'affinage",
      llm_temperature: 'Température',
      draft_think: 'Réflexion (draft)',
      refine_think: 'Réflexion (affinage)',
      default_target_language: 'Langue cible',
      sliding_window_size: 'Fenêtre glissante',
      batch_size: 'Taille de batch',
      cps_limit: 'Limite CPS',
      auto_clean_sdh: 'Nettoyage SDH',
      tmdb_api_key: 'Clé API TMDB',
    };
    return map[key] || key.replaceAll('_', ' ');
  };

  if (loading) return (
    <div className="flex items-center justify-center py-32 text-gray-600">
      <div className="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
    </div>
  );

  return (
    <div className="animate-fade-in">
      <_ToastBar />
      {/* Header + Save */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-100 tracking-tight">Paramètres</h1>
          <p className="text-sm text-gray-500 mt-1">Configuration de Kinoscribe — tout se gère ici</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className={`btn-primary self-start sm:self-auto ${
            saved ? '!bg-emerald-600 hover:!bg-emerald-500 !shadow-emerald-600/25' : ''
          }`}
        >
          {saving ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : saved ? (
            <CheckCircle2 className="w-4 h-4" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          {saving ? 'Sauvegarde…' : saved ? 'Enregistré !' : 'Enregistrer'}
        </button>
      </div>

      {/* ── Settings grid — 2 columns on wide screens ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {Object.entries(categories).map(([cat, items]) => {
          const config = categoryConfig[cat] || { label: cat, icon: Box, description: '' };
          const Icon = config.icon;
          const isLlm = cat === 'llm';

          return (
            <div key={cat} className={isLlm ? 'lg:col-span-2' : ''}>
              {/* Category header */}
              <div className="flex items-center gap-3 mb-4">
                <div className={`flex items-center justify-center w-8 h-8 rounded-lg ${
                  isLlm ? 'bg-brand-500/15' : 'bg-white/[0.04]'
                }`}>
                  <Icon className={`w-4 h-4 ${isLlm ? 'text-brand-400' : 'text-gray-500'}`} />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-gray-200">{config.label}</h2>
                  <p className="text-[11px] text-gray-600">{config.description}</p>
                </div>
              </div>

              {/* Settings card */}
              <div className="glass-card divide-y divide-white/[0.04] overflow-hidden">
                {items.map((s) => (
                  <div key={s.key} className="px-5 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-6">
                    {/* Label + description */}
                    <div className="min-w-0 sm:w-1/3">
                      <label className="text-sm font-semibold text-gray-200">{prettyLabel(s.key)}</label>
                      {s.description && (
                        <p className="text-xs text-gray-600 mt-0.5 leading-relaxed">{s.description}</p>
                      )}
                    </div>

                    {/* Input */}
                    <div className="sm:w-2/3">
                      {modelKeys.has(s.key) ? (
                        <ModelSelect
                          value={form[s.key] || ''}
                          models={ollamaModels}
                          onChange={(v) => set(s.key, v)}
                        />
                      ) : s.input_type === 'select' && s.options ? (
                        <select
                          value={form[s.key] || ''}
                          onChange={(e) => set(s.key, e.target.value)}
                          className="select-field"
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
                          className="input-field"
                        />
                      ) : s.key === 'ollama_base_url' ? (
                        <div className="relative">
                          <input
                            type="url"
                            value={form[s.key] || ''}
                            onChange={(e) => handleUrlChange(e.target.value)}
                            placeholder="http://host:11434"
                            className="input-field !pr-10"
                          />
                          {fetchingModels && (
                            <span className="absolute right-3 top-1/2 -translate-y-1/2">
                              <div className="w-4 h-4 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
                            </span>
                          )}
                        </div>
                      ) : (
                        <input
                          type={s.input_type === 'number' ? 'number' : 'text'}
                          value={form[s.key] || ''}
                          onChange={(e) => set(s.key, e.target.value)}
                          step={s.input_type === 'number' ? 'any' : undefined}
                          className="input-field"
                        />
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Ollama extras */}
              {isLlm && (
                <div className="mt-4 space-y-3 px-1">
                  <div className="flex items-center gap-3 flex-wrap">
                    <button
                      onClick={handleTestOllama}
                      disabled={testing}
                      className={ollamaTest?.ok ? 'btn-secondary' : 'btn-primary'}
                    >
                      {testing ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : ollamaTest?.ok ? (
                        <Wifi className="w-4 h-4 text-emerald-400" />
                      ) : (
                        <WifiOff className="w-4 h-4" />
                      )}
                      {testing ? 'Test en cours…' : 'Tester la connexion'}
                    </button>
                    {ollamaTest && (
                      <div className={`text-sm ${ollamaTest.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                        {ollamaTest.ok ? (
                          <>
                            ✅ Connecté — {ollamaTest.models?.length || 0} modèle(s)
                            {ollamaTest.models && ollamaTest.models.length > 0 && (
                              <span className="text-gray-600 ml-1">
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

                  {modelsError && (
                    <p className="text-xs text-red-400">⚠️ Impossible de charger les modèles : {modelsError}</p>
                  )}
                  {ollamaModels.length > 0 && !fetchingModels && (
                    <p className="text-xs text-gray-500">
                      📦 {ollamaModels.length} modèle(s) disponible(s) — utilisez les listes déroulantes ci-dessus
                    </p>
                  )}
                  {ollamaModels.length === 0 && !fetchingModels && form.ollama_base_url && !modelsError && (
                    <p className="text-xs text-yellow-500/80">
                      💡 Aucun modèle trouvé. Vérifiez l'URL ou tirez un modèle avec{' '}
                      <code className="bg-white/[0.04] px-1.5 py-0.5 rounded text-yellow-400">ollama pull &lt;model&gt;</code>
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Sticky save bar for mobile */}
      <div className="lg:hidden sticky bottom-0 mt-8 -mx-4 sm:-mx-6 lg:-mx-8 xl:-mx-10 px-4 py-4 bg-surface-0/80 backdrop-blur-xl border-t border-white/[0.06]">
        <button
          onClick={handleSave}
          disabled={saving}
          className={`btn-primary w-full justify-center ${
            saved ? '!bg-emerald-600 hover:!bg-emerald-500' : ''
          }`}
        >
          {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle2 className="w-4 h-4" /> : <Save className="w-4 h-4" />}
          {saving ? 'Sauvegarde…' : saved ? 'Enregistré !' : 'Enregistrer les paramètres'}
        </button>
      </div>
    </div>
  );
}

// ── Model select with dropdown + manual input ──
function ModelSelect({
  value,
  models,
  onChange,
}: {
  value: string;
  models: string[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-2">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="select-field"
      >
        <option value="" disabled>
          {models.length > 0 ? '— Choisir un modèle —' : 'Aucun modèle trouvé'}
        </option>
        {models.map((model) => (
          <option key={model} value={model}>{model}</option>
        ))}
        {value && !models.includes(value) && (
          <option value={value}>{value} (non listé)</option>
        )}
      </select>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="ou saisir manuellement…"
        className="input-field !py-1.5 !text-xs !bg-white/[0.02] text-gray-400"
      />
    </div>
  );
}