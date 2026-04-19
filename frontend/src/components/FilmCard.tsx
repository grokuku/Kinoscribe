import type { Film } from '../types';
import { Link } from 'react-router-dom';
import { Film as FilmIcon, Languages, Users } from 'lucide-react';

export default function FilmCard({ film }: { film: Film }) {
  return (
    <Link
      to={`/films/${film.id}`}
      className="group block border border-gray-800 rounded-xl p-5 hover:border-brand-600/50 hover:bg-gray-900/50 transition-all"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <FilmIcon className="w-5 h-5 text-brand-400" />
          <h3 className="text-lg font-semibold text-gray-100 group-hover:text-brand-300 transition-colors">
            {film.title}
          </h3>
        </div>
        {film.year && (
          <span className="text-sm text-gray-500 bg-gray-800 px-2 py-0.5 rounded-md">
            {film.year}
          </span>
        )}
      </div>

      {film.director && (
        <p className="text-sm text-gray-400 mb-2">Réalisé par {film.director}</p>
      )}
      {film.summary && (
        <p className="text-sm text-gray-500 line-clamp-2 mb-3">{film.summary}</p>
      )}

      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1">
          <Languages className="w-3.5 h-3.5" />
          {film.source_language.toUpperCase()} → {film.target_language.toUpperCase()}
        </span>
        {film.characters.length > 0 && (
          <span className="flex items-center gap-1">
            <Users className="w-3.5 h-3.5" />
            {film.characters.length} perso.
          </span>
        )}
      </div>
    </Link>
  );
}