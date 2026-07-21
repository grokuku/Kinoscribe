import { useParams, Link } from 'react-router-dom';
import { useTask, useLiveTranslation } from '../hooks/useApi';
import { StatusBadge, TaskProgressBar } from '../components/TaskStatus';
import SubtitleViewer from '../components/SubtitleViewer';
import { CheckCircle2, ArrowLeft, ExternalLink, Loader2, AlertCircle } from 'lucide-react';

export default function TaskLivePage() {
  const { taskId } = useParams<{ taskId: string }>();

  // Fetch task metadata (for film title, etc.)
  const { data: task, loading: taskLoading, error: taskError } = useTask(taskId ?? '');

  // Live content polling
  const {
    lines,
    loading: contentLoading,
    error: contentError,
    taskStatus,
    progress,
    isActive,
  } = useLiveTranslation(taskId ?? '');

  // Loading state (initial)
  if (taskLoading && !task) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="w-8 h-8 text-brand-400 animate-spin" />
      </div>
    );
  }

  // Error loading task
  if (taskError) {
    return (
      <div className="py-16 text-center">
        <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
        <p className="text-red-400">Erreur : {taskError}</p>
        <Link to="/tasks" className="btn-secondary mt-6 inline-flex">
          <ArrowLeft className="w-4 h-4" />
          Retour aux tâches
        </Link>
      </div>
    );
  }

  if (!taskId || !task) {
    return (
      <div className="py-16 text-center">
        <p className="text-gray-500">Tâche introuvable.</p>
        <Link to="/tasks" className="btn-secondary mt-6 inline-flex">
          <ArrowLeft className="w-4 h-4" />
          Retour aux tâches
        </Link>
      </div>
    );
  }

  const isTerminal = taskStatus === 'completed' || taskStatus === 'failed';
  const isError = !!contentError;

  return (
    <div className="animate-fade-in max-w-4xl mx-auto space-y-6">
      {/* Back link */}
      <Link
        to="/tasks"
        className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Retour aux tâches
      </Link>

      {/* Header card */}
      <div className="glass-card p-6 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="space-y-2 min-w-0">
            <h1 className="text-xl font-bold text-gray-100 truncate">
              Suivi en direct
            </h1>
            <div className="flex items-center gap-3 flex-wrap">
              <StatusBadge status={taskStatus ?? task.status} />
              <span className="text-sm text-gray-500 font-mono truncate">
                {task.source_filename}
              </span>
              {task.film_title && (
                <Link
                  to={`/films/${task.film_id}`}
                  className="inline-flex items-center gap-1 text-xs text-brand-400 hover:text-brand-300 transition-colors"
                >
                  {task.film_title}
                  <ExternalLink className="w-3 h-3" />
                </Link>
              )}
            </div>
          </div>

          {/* Line count */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="text-right">
              <div className="text-2xl font-bold tabular-nums text-gray-100">
                {lines.length}
              </div>
              <div className="text-xs text-gray-500">lignes traduites</div>
            </div>
          </div>
        </div>

        {/* Progress bar */}
        <TaskProgressBar
          status={taskStatus ?? task.status}
          progress={progress}
        />

        {/* Error message */}
        {isError && (
          <div className="flex items-start gap-3 px-4 py-3 bg-red-500/10 ring-1 ring-red-500/20 rounded-xl text-sm text-red-400">
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <span>{contentError}</span>
          </div>
        )}
      </div>

      {/* Terminal state: completed */}
      {isTerminal && (
        <div className="glass-card p-6 text-center space-y-4">
          {taskStatus === 'completed' && (
            <>
              <div className="flex items-center justify-center gap-3">
                <div className="flex items-center justify-center w-12 h-12 rounded-full bg-emerald-500/10">
                  <CheckCircle2 className="w-7 h-7 text-emerald-400" />
                </div>
                <div className="text-left">
                  <h2 className="text-lg font-semibold text-emerald-300">
                    Traduction terminée !
                  </h2>
                  <p className="text-sm text-gray-500">
                    {lines.length} ligne{lines.length !== 1 ? 's' : ''} traduite{lines.length !== 1 ? 's' : ''} au total
                  </p>
                </div>
              </div>
              <div className="flex items-center justify-center gap-3">
                <a
                  href={`/api/tasks/${taskId}/download`}
                  className="btn-primary !bg-emerald-600 hover:!bg-emerald-500 !shadow-emerald-600/25"
                >
                  <ExternalLink className="w-4 h-4" />
                  Télécharger .srt
                </a>
                <Link
                  to="/tasks"
                  className="btn-secondary"
                >
                  Voir dans l'historique
                </Link>
              </div>
            </>
          )}
          {taskStatus === 'failed' && (
            <div className="text-center">
              <AlertCircle className="w-10 h-10 text-red-400 mx-auto mb-3" />
              <h2 className="text-lg font-semibold text-red-300 mb-1">
                Échec de la traduction
              </h2>
              {task.error_message && (
                <p className="text-sm text-red-400/80 max-w-md mx-auto mb-4">
                  {task.error_message}
                </p>
              )}
              <Link to="/tasks" className="btn-secondary">
                <ArrowLeft className="w-4 h-4" />
                Retour aux tâches
              </Link>
            </div>
          )}
        </div>
      )}

      {/* Live subtitle viewer */}
      <SubtitleViewer lines={lines} loading={contentLoading && isActive} />

      {/* Active polling indicator */}
      {isActive && (
        <div className="flex items-center justify-center gap-2 text-xs text-gray-600 pb-4">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-brand-500" />
          </span>
          Mise à jour en temps réel
        </div>
      )}
    </div>
  );
}
