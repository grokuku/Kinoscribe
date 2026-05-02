import type { Film } from '../types';
import { Link } from 'react-router-dom';
import { Film as FilmIcon, Languages, Users, ArrowRight, FolderOpen } from 'lucide-react';

// Poster URL helper
function posterUrl(film: Film): string | null {
  if (!film.poster_path) return null;
  return `/api/films/${film.id}/poster`;
}

export default function FilmCard({ film }: { film: Film }) {
  const poster = posterUrl(film);

  return (
    <Link
      to={`/films/${film.id}`}
      className="group relative glass-card-hover overflow-hidden flex flex-col animate-fade-in"
    >
      {/* Poster image or gradient placeholder */}
      {poster ? (
        <div className="relative w-full aspect-[2/3] bg-gray-900 overflow-hidden">
          <img
            src={poster}
            alt={film.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            loading="lazy"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
              const parent = (e.target as HTMLImageElement).parentElement;
              if (parent) parent.classList.add('poster-fallback');
            }}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent" />
        </div>
      ) : (
        <div className="relative w-full aspect-[2/3] bg-gradient-to-br from-gray-800/50 to-gray-900/80 flex items-center justify-center">
          <FilmIcon className="w-12 h-12 text-gray-700/50" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
        </div>
      )}

      {/* Info overlay at bottom */}
      <div className="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-black/90 via-black/60 to-transparent">
        <h3 className="text-sm font-bold text-white truncate">{film.title}</h3>
        <div className="flex items-center gap-2 mt-0.5">
          {film.year && <span className="text-[11px] font-mono text-gray-300">{film.year}</span>}
          {film.director && <span className="text-[11px] text-gray-400 truncate">de {film.director}</span>}
        </div>
      </div>

      {/* Bottom meta bar */}
      <div className="flex items-center justify-between px-3 py-2 bg-white/[0.02] border-t border-white/[0.04]">
        <div className="flex items-center gap-3 text-[11px]">
          <span className="flex items-center gap-1 text-gray-400">
            <Languages className="w-3 h-3 text-brand-400/70" />
            <span className="font-mono">{film.source_language.toUpperCase()}→{film.target_language.toUpperCase()}</span>
          </span>
          {film.characters?.length > 0 && (
            <span className="flex items-center gap-1 text-gray-500">
              <Users className="w-3 h-3" />{film.characters.length}
            </span>
          )}
          {film.path && (
            <span className="flex items-center gap-1 text-gray-600" title={film.path}>
              <FolderOpen className="w-3 h-3" />
            </span>
          )}
        </div>
        <ArrowRight className="w-3.5 h-3.5 text-gray-600 group-hover:text-brand-400 transition-colors" />
      </div>
    </Link>
  );
}