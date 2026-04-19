import { useState } from 'react';
import { Plus } from 'lucide-react';
import { useFilms } from '../hooks/useApi';
import { api } from '../api/client';
import type { FilmCreate } from '../types';
import FilmCard from '../components/FilmCard';
import CreateFilmModal from '../components/CreateFilmModal';

export default function FilmsPage() {
  const { data: films, loading, error, refresh } = useFilms();
  const [modalOpen, setModalOpen] = useState(false);
  const [creating, setCreating] = useState(false);

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

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">Films</h1>
          <p className="text-sm text-gray-500 mt-1">
            Gérez vos films et lancez des traductions de sous-titres
          </p>
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Ajouter un film
        </button>
      </div>

      {/* Content */}
      {loading && films === null && (
        <div className="text-center py-16 text-gray-500">Chargement…</div>
      )}
      {error && (
        <div className="text-center py-16 text-red-400">Erreur : {error}</div>
      )}
      {films && films.length === 0 && (
        <div className="text-center py-20">
          <div className="text-gray-600 text-5xl mb-4">🎬</div>
          <p className="text-gray-500 mb-4">Aucun film enregistré</p>
          <button
            onClick={() => setModalOpen(true)}
            className="text-brand-400 hover:text-brand-300 text-sm font-medium"
          >
            + Ajouter votre premier film
          </button>
        </div>
      )}
      {films && films.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {films.map((film) => (
            <FilmCard key={film.id} film={film} />
          ))}
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