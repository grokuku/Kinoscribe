import { useState } from 'react';
import { X } from 'lucide-react';
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-gray-100">Nouveau film</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">Titre *</label>
            <input
              required
              value={form.title}
              onChange={(e) => set('title', e.target.value)}
              className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-gray-100 focus:outline-none focus:border-brand-500"
              placeholder="Ex: The Shawshank Redemption"
            />
          </div>

          {/* Year + Director row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">Année</label>
              <input
                type="number"
                value={form.year ?? ''}
                onChange={(e) => set('year', e.target.value ? parseInt(e.target.value) : null)}
                className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-gray-100 focus:outline-none focus:border-brand-500"
                placeholder="1994"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">Réalisateur</label>
              <input
                value={form.director ?? ''}
                onChange={(e) => set('director', e.target.value)}
                className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-gray-100 focus:outline-none focus:border-brand-500"
                placeholder="Frank Darabont"
              />
            </div>
          </div>

          {/* Languages row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">Langue source</label>
              <select
                value={form.source_language}
                onChange={(e) => set('source_language', e.target.value)}
                className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-gray-100 focus:outline-none focus:border-brand-500"
              >
                {['en','es','de','it','pt','ja','ko','zh'].map((l) => (
                  <option key={l} value={l}>{l.toUpperCase()}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">Langue cible</label>
              <select
                value={form.target_language}
                onChange={(e) => set('target_language', e.target.value)}
                className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-gray-100 focus:outline-none focus:border-brand-500"
              >
                {['fr','en','es','de','it','pt'].map((l) => (
                  <option key={l} value={l}>{l.toUpperCase()}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Summary */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">Résumé</label>
            <textarea
              rows={2}
              value={form.summary ?? ''}
              onChange={(e) => set('summary', e.target.value)}
              className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-gray-100 focus:outline-none focus:border-brand-500 resize-none"
              placeholder="Synopsis court (optionnel)"
            />
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200 transition-colors"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {loading ? 'Création…' : 'Créer le film'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}