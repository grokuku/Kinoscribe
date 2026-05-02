import { useState } from 'react';
import { X, Film, Save } from 'lucide-react';
import type { FilmCreate } from '../types';

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: FilmCreate) => void;
  loading?: boolean;
}

export default function CreateFilmModal({ open, onClose, onSubmit, loading }: Props) {
  const [form, setForm] = useState<FilmCreate>({
    title: '',
    year: null,
    director: '',
    summary: '',
    source_language: 'en',
    target_language: 'fr',
  });

  if (!open) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) return;
    onSubmit(form);
  };

  const set = (key: keyof FilmCreate, val: any) =>
    setForm((f) => ({ ...f, [key]: val }));

  const languages = [
    { code: 'en', label: 'EN', name: 'Anglais' },
    { code: 'fr', label: 'FR', name: 'Français' },
    { code: 'es', label: 'ES', name: 'Espagnol' },
    { code: 'de', label: 'DE', name: 'Allemand' },
    { code: 'it', label: 'IT', name: 'Italien' },
    { code: 'pt', label: 'PT', name: 'Portugais' },
    { code: 'ja', label: 'JA', name: 'Japonais' },
    { code: 'ko', label: 'KO', name: 'Coréen' },
    { code: 'zh', label: 'ZH', name: 'Chinois' },
  ];
  const sourceLangs = languages.filter((l) => ['en', 'es', 'de', 'it', 'pt', 'ja', 'ko', 'zh'].includes(l.code));
  const targetLangs = languages.filter((l) => ['fr', 'en', 'es', 'de', 'it', 'pt'].includes(l.code));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-xl glass-card p-0 animate-slide-up shadow-2xl shadow-black/50 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-brand-500/15">
              <Film className="w-5 h-5 text-brand-400" />
            </div>
            <h2 className="text-lg font-bold text-gray-100">Nouveau film</h2>
          </div>
          <button onClick={onClose} className="btn-ghost !p-1.5 rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {/* Title */}
          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Titre *</label>
            <input
              required
              value={form.title}
              onChange={(e) => set('title', e.target.value)}
              className="input-field text-base"
              placeholder="Ex: The Shawshank Redemption"
            />
          </div>

          {/* Year + Director */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Année</label>
              <input
                type="number"
                value={form.year ?? ''}
                onChange={(e) => set('year', e.target.value ? parseInt(e.target.value) : null)}
                className="input-field"
                placeholder="1994"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Réalisateur</label>
              <input
                value={form.director ?? ''}
                onChange={(e) => set('director', e.target.value)}
                className="input-field"
                placeholder="Frank Darabont"
              />
            </div>
          </div>

          {/* Languages */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Langue source</label>
              <select
                value={form.source_language}
                onChange={(e) => set('source_language', e.target.value)}
                className="select-field"
              >
                {sourceLangs.map((l) => (
                  <option key={l.code} value={l.code}>{l.label} — {l.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Langue cible</label>
              <select
                value={form.target_language}
                onChange={(e) => set('target_language', e.target.value)}
                className="select-field"
              >
                {targetLangs.map((l) => (
                  <option key={l.code} value={l.code}>{l.label} — {l.name}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Summary */}
          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Résumé</label>
            <textarea
              rows={3}
              value={form.summary ?? ''}
              onChange={(e) => set('summary', e.target.value)}
              className="input-field resize-none"
              placeholder="Synopsis court (optionnel)"
            />
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary">
              Annuler
            </button>
            <button type="submit" disabled={loading} className="btn-primary">
              <Save className="w-4 h-4" />
              {loading ? 'Création…' : 'Créer le film'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}