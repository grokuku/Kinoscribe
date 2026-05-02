import { useState } from 'react';
import { Plus, Search, Film as FilmIcon } from 'lucide-react';
import { useFilms } from '../hooks/useApi';
import { api } from '../api/client';
import type { FilmCreate } from '../types';
import FilmCard from '../components/FilmCard';
import CreateFilmModal from '../components/CreateFilmModal';

export default function FilmsPage() {
  const { data: films, loading, error, refresh } = useFilms();
  const [modalOpen, setModalOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState('');

  const handleCreate = async (data: FilmCreate) => {
    setCreating(true);
    try {
      await api.createFilm(data);
      setModalOpen(false);
      refresh();
    } catch (e: any) {
      alert('Erreur: ' + e.message);
    } finally {
      setCreating(false);
    }
  };

  const filtered = films?.filter((f) =>
    f.title.toLowerCase().includes(search.toLowerCase()) ||
    (f.director && f.director.toLowerCase().includes(search.toLowerCase()))
  ) ?? [];

  return (
    <div className="animate-fade-in">
      {/* Hero header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-100 tracking-tight">Films</h1>
          <p className="text-sm text-gray-500 mt-1">
            Gérez vos films et lancez des traductions de sous-titres
          </p>
        </div>
        <button onClick={() => setModalOpen(true)} className="btn-primary self-start sm:self-auto">
          <Plus className="w-4 h-4" />
          Ajouter un film
        </button>
      </div>

      {/* Search (only if films exist) */}
      {films && films.length > 0 && (
        <div className="relative mb-6 max-w-md">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher un film…"
            className="input-field !pl-10"
          />
        </div>
      )}

      {/* States */}
      {loading && !films && (
        <div className="flex items-center justify-center py-32 text-gray-600">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
            <span className="text-sm">Chargement…</span>
          </div>
        </div>
      )}
      {error && (
        <div className="flex items-center justify-center py-32 text-red-400">
          <p>Erreur : {error}</p>
        </div>
      )}

      {/* Empty state */}
      {films && films.length === 0 && (
        <div className="flex flex-col items-center justify-center py-32 text-center">
          <div className="flex items-center justify-center w-20 h-20 rounded-3xl bg-white/[0.03] mb-6">
            <FilmIcon className="w-10 h-10 text-gray-700" />
          </div>
          <h2 className="text-xl font-semibold text-gray-400 mb-2">Aucun film enregistré</h2>
          <p className="text-sm text-gray-600 mb-6 max-w-sm">
            Ajoutez votre premier film pour commencer à traduire des sous-titres avec l'aide de l'IA.
          </p>
          <button onClick={() => setModalOpen(true)} className="btn-primary">
            <Plus className="w-4 h-4" />
            Ajouter un film
          </button>
        </div>
      )}

      {/* Film grid — fills the entire width */}
      {filtered.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4">
          {filtered.map((film, i) => (
            <div key={film.id} style={{ animationDelay: `${i * 40}ms` }} className="animate-slide-up">
              <FilmCard film={film} />
            </div>
          ))}
        </div>
      )}

      {/* No search results */}
      {films && films.length > 0 && filtered.length === 0 && (
        <div className="text-center py-16 text-gray-600">
          <p>Aucun résultat pour « {search} »</p>
        </div>
      )}

      <CreateFilmModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubmit={handleCreate}
        loading={creating}
      />
    </div>
  );
}