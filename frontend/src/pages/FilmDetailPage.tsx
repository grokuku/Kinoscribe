import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Trash2, Users, Languages, Play, Download, BookOpen,
} from 'lucide-react';
import { useFilm, useTasks } from '../hooks/useApi';
import { api } from '../api/client';
import { StatusBadge, TaskProgressBar } from '../components/TaskStatus';
import SubtitleUploader from '../components/SubtitleUploader';
import type { Task } from '../types';

export default function FilmDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: film, loading, error, refresh: refreshFilm } = useFilm(id!);
  const { data: tasks, refresh: refreshTasks } = useTasks();
  const [uploading, setUploading] = useState(false);
  const [starting, setStarting] = useState<string | null>(null);

  const filmTasks = tasks?.filter((t) => t.film_id === id) ?? [];

  // Upload handler
  const handleUpload = async (file: File, sourceLang: string) => {
    setUploading(true);
    try {
      await api.uploadSubtitle(film!.id, file, sourceLang);
      refreshTasks();
      refreshFilm();
    } catch (e: any) {
      alert('Upload erreur : ' + e.message);
    } finally {
      setUploading(false);
    }
  };

  // Start translation
  const handleStart = async (taskId: string) => {
    setStarting(taskId);
    try {
      await api.startTranslation(taskId);
      refreshTasks();
    } catch (e: any) {
      alert('Démarrage erreur : ' + e.message);
    } finally {
      setStarting(null);
    }
  };

  // Delete film
  const handleDelete = async () => {
    if (!confirm(`Supprimer "${film!.title}" et toutes ses données ?`)) return;
    try {
      await api.deleteFilm(film!.id);
      navigate('/');
    } catch (e: any) {
      alert('Suppression erreur : ' + e.message);
    }
  };

  if (loading) return <div className="py-16 text-center text-gray-500">Chargement…</div>;
  if (error || !film) return <div className="py-16 text-center text-red-400">Film introuvable</div>;

  const pendingTasks = filmTasks.filter((t) => t.status === 'pending' || t.status === 'failed');

  return (
    <div>
      {/* Back + Header */}
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-300 mb-4">
        <ArrowLeft className="w-4 h-4" /> Retour aux films
      </Link>

      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">{film.title}</h1>
          <div className="flex items-center gap-3 mt-1 text-sm text-gray-500">
            {film.year && <span>{film.year}</span>}
            {film.director && <span>· Réalisé par {film.director}</span>}
            <span className="flex items-center gap-1">
              <Languages className="w-3.5 h-3.5" />
              {film.source_language.toUpperCase()} → {film.target_language.toUpperCase()}
            </span>
          </div>
          {film.summary && <p className="text-gray-500 mt-2 text-sm">{film.summary}</p>}
        </div>
        <button
          onClick={handleDelete}
          className="text-gray-600 hover:text-red-400 transition-colors p-2"
          title="Supprimer"
        >
          <Trash2 className="w-5 h-5" />
        </button>
      </div>

      {/* Characters */}
      {film.characters.length > 0 && (
        <div className="mb-6">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-300 mb-3">
            <Users className="w-4 h-4" /> Personnages identifiés
          </h2>
          <div className="flex flex-wrap gap-2">
            {film.characters.map((c) => (
              <span
                key={c.name}
                className={`px-3 py-1 rounded-full text-xs font-medium ${
                  c.gender === 'male'
                    ? 'bg-blue-900/40 text-blue-300'
                    : c.gender === 'female'
                      ? 'bg-pink-900/40 text-pink-300'
                      : 'bg-gray-800 text-gray-400'
                }`}
                title={c.description || c.gender}
              >
                {c.name} ({c.gender})
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Upload zone */}
      <div className="mb-6">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">Ajouter des sous-titres</h2>
        <SubtitleUploader onUpload={handleUpload} disabled={uploading} />
        {uploading && <p className="text-sm text-brand-400 mt-2">Upload en cours…</p>}
      </div>

      {/* Tasks */}
      <div className="mb-6">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">Tâches de traduction</h2>
        {filmTasks.length === 0 ? (
          <p className="text-sm text-gray-600">Aucune tâche — uploadez un fichier sous-titre pour commencer.</p>
        ) : (
          <div className="space-y-3">
            {filmTasks.map((task) => (
              <TaskRow
                key={task.id}
                task={task}
                onStart={handleStart}
                starting={starting === task.id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Task row component ────────────────────────────────────────

function TaskRow({
  task,
  onStart,
  starting,
}: {
  task: Task;
  onStart: (id: string) => void;
  starting: boolean;
}) {
  const canStart = task.status === 'pending' || task.status === 'failed';
  const isRunning = ['analyzing_context', 'translating', 'refining'].includes(task.status);

  return (
    <div className="border border-gray-800 rounded-xl p-4 space-y-3">
      {/* Top row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <StatusBadge status={task.status} />
          <span className="text-sm text-gray-300 font-mono">{task.source_filename}</span>
        </div>
        <div className="flex items-center gap-2">
          {canStart && (
            <button
              onClick={() => onStart(task.id)}
              disabled={starting}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-md transition-colors"
            >
              <Play className="w-3.5 h-3.5" />
              {starting ? 'Démarrage…' : 'Traduire'}
            </button>
          )}
          {task.status === 'completed' && task.target_filename && (
            <a
              href={`/api/tasks/${task.id}/download`}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-md transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              Télécharger
            </a>
          )}
        </div>
      </div>

      {/* Progress bar */}
      {(isRunning || task.status === 'completed') && (
        <TaskProgressBar status={task.status} progress={task.progress_pct} />
      )}

      {/* Error */}
      {task.error_message && (
        <p className="text-xs text-red-400 bg-red-900/20 rounded-md px-3 py-2">
          {task.error_message}
        </p>
      )}
    </div>
  );
}