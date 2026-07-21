import { useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useTasks, useDeleteTask, useTaskContent } from '../hooks/useApi';
import { StatusBadge, TaskProgressBar } from '../components/TaskStatus';
import {
  Download, Eye, Activity, CheckCircle2, Clock, AlertCircle, Zap,
  Trash2, X, ChevronRight
} from 'lucide-react';
import type { Task, SubtitleLine } from '../types';

type ActiveTab = 'all' | 'active' | 'completed' | 'failed';

export default function TasksPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('all');
  const { data: tasks, loading, error, refresh } = useTasks();
  const { deleteTask, loading: deleting } = useDeleteTask();
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  // ── Content preview modal ──
  const [previewTaskId, setPreviewTaskId] = useState<string | null>(null);
  const { data: contentLines, loading: contentLoading } = useTaskContent(previewTaskId);

  const handleDelete = useCallback(async (taskId: string) => {
    try {
      await deleteTask(taskId);
      refresh();
    } catch {
      // error is handled in hook
    } finally {
      setConfirmDelete(null);
    }
  }, [deleteTask, refresh]);

  const openPreview = useCallback((taskId: string) => {
    setPreviewTaskId(taskId);
  }, []);

  const closePreview = useCallback(() => {
    setPreviewTaskId(null);
  }, []);

  if (loading && !tasks) return (
    <div className="flex items-center justify-center py-32 text-gray-600">
      <div className="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
    </div>
  );
  if (error) return <div className="py-16 text-center text-red-400">Erreur : {error}</div>;

  const all = tasks ?? [];

  // Stats
  const active = all.filter((t) =>
    ['analyzing_context', 'translating', 'refining', 'extracting', 'transcribing', 'syncing', 'rescanning'].includes(t.status)
  );
  const completed = all.filter((t) => t.status === 'completed');
  const pending = all.filter((t) => t.status === 'pending');
  const failed = all.filter((t) => t.status === 'failed');

  // Filtered list based on active tab
  let filtered: Task[];
  switch (activeTab) {
    case 'active':
      filtered = active;
      break;
    case 'completed':
      filtered = completed;
      break;
    case 'failed':
      filtered = failed;
      break;
    default:
      filtered = all;
      break;
  }

  const tabs: { key: ActiveTab; label: string; count: number }[] = [
    { key: 'all', label: 'Toutes', count: all.length },
    { key: 'active', label: 'En cours', count: active.length },
    { key: 'completed', label: 'Terminées', count: completed.length },
    { key: 'failed', label: 'Échouées', count: failed.length },
  ];

  return (
    <div className="animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-100 tracking-tight">Tâches de traduction</h1>
          <p className="text-sm text-gray-500 mt-1">Suivez l'avancement de vos traductions</p>
        </div>
        <button onClick={refresh} className="btn-secondary self-start sm:self-auto">
          <Activity className="w-4 h-4" />
          Actualiser
        </button>
      </div>

      {tasks && tasks.length === 0 && (
        <div className="flex flex-col items-center justify-center py-32 text-center">
          <div className="flex items-center justify-center w-20 h-20 rounded-3xl bg-white/[0.03] mb-6">
            <Clock className="w-10 h-10 text-gray-700" />
          </div>
          <h2 className="text-xl font-semibold text-gray-400 mb-2">Aucune tâche</h2>
          <p className="text-sm text-gray-600 max-w-sm">
            Uploadez un sous-titre depuis la page d'un film pour lancer une traduction.
          </p>
        </div>
      )}

      {/* Stats bar — full width */}
      {tasks && tasks.length > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
            <StatCard icon={<Zap className="w-5 h-5 text-brand-400" />} value={active.length} label="En cours" color="brand" />
            <StatCard icon={<Clock className="w-5 h-5 text-gray-400" />} value={pending.length} label="En attente" color="gray" />
            <StatCard icon={<CheckCircle2 className="w-5 h-5 text-emerald-400" />} value={completed.length} label="Terminées" color="emerald" />
            <StatCard icon={<AlertCircle className="w-5 h-5 text-red-400" />} value={failed.length} label="Échouées" color="red" />
          </div>

          {/* Tabs */}
          <div className="flex gap-1 mb-6 border-b border-white/[0.06]">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-4 py-2.5 text-sm font-medium transition-all duration-200 border-b-2 -mb-px ${
                  activeTab === tab.key
                    ? 'text-brand-400 border-brand-500'
                    : 'text-gray-500 border-transparent hover:text-gray-300 hover:border-gray-600'
                }`}
              >
                {tab.label}
                <span className="ml-2 text-xs opacity-60">{tab.count}</span>
              </button>
            ))}
          </div>

          {/* Task grid */}
          {filtered.length === 0 && (
            <div className="py-16 text-center text-gray-500">
              Aucune tâche dans cette catégorie.
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
            {filtered.map((t) => (
              <TaskCard
                key={t.id}
                task={t}
                onDelete={t.status === 'completed' || t.status === 'failed' ? () => setConfirmDelete(t.id) : undefined}
                onPreview={t.status === 'completed' ? () => openPreview(t.id) : undefined}
              />
            ))}
          </div>
        </>
      )}

      {/* Confirm delete dialog */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="glass-card p-6 max-w-sm w-full space-y-4">
            <h3 className="text-lg font-semibold text-gray-100">Confirmer la suppression</h3>
            <p className="text-sm text-gray-400">
              Êtes-vous sûr de vouloir supprimer cette tâche ? Cette action est irréversible.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmDelete(null)}
                className="btn-ghost"
              >
                Annuler
              </button>
              <button
                onClick={() => handleDelete(confirmDelete)}
                disabled={deleting}
                className="btn-primary !bg-red-600 hover:!bg-red-500 !shadow-red-600/25"
              >
                {deleting ? 'Suppression...' : 'Supprimer'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Content preview modal */}
      {previewTaskId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
          onClick={closePreview}
        >
          <div
            className="glass-card p-6 w-full max-w-4xl max-h-[85vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-100">Aperçu du sous-titre</h3>
              <button
                onClick={closePreview}
                className="btn-ghost p-1.5"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {contentLoading && (
              <div className="flex items-center justify-center py-16">
                <div className="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
              </div>
            )}

            {!contentLoading && contentLines && (
              <div className="overflow-y-auto flex-1 space-y-1 font-mono text-sm">
                {contentLines.map((line) => (
                  <SubtitleLineRow key={line.index} line={line} />
                ))}
              </div>
            )}

            {!contentLoading && !contentLines && (
              <div className="py-16 text-center text-gray-500">
                Aucun contenu disponible.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function SubtitleLineRow({ line }: { line: SubtitleLine }) {
  return (
    <div className="flex gap-3 px-3 py-1.5 rounded-lg hover:bg-white/[0.03] group">
      <span className="text-gray-500 w-8 text-right flex-shrink-0 select-none">
        {line.index}
      </span>
      <span className="text-gray-500 w-36 flex-shrink-0 font-mono text-xs select-none">
        {line.start} → {line.end}
      </span>
      <span className="text-gray-200 break-words">
        {line.text}
      </span>
    </div>
  );
}

function StatCard({ icon, value, label, color }: { icon: React.ReactNode; value: number; label: string; color: string }) {
  return (
    <div className="glass-card p-5 flex items-center gap-4">
      <div className={`flex items-center justify-center w-11 h-11 rounded-xl bg-${color}-500/10`}>
        {icon}
      </div>
      <div>
        <div className="stat-value !text-2xl">{value}</div>
        <div className="text-xs text-gray-600 mt-0.5">{label}</div>
      </div>
    </div>
  );
}

function TaskCard({
  task,
  onDelete,
  onPreview,
}: {
  task: Task;
  onDelete?: () => void;
  onPreview?: () => void;
}) {
  const isRunning = ['analyzing_context', 'translating', 'refining', 'extracting', 'transcribing', 'syncing', 'rescanning'].includes(task.status);
  const isPendingOrRunning = isRunning || task.status === 'pending';

  const handleClick = () => {
    if (task.status === 'completed' && onPreview) {
      onPreview();
    }
  };

  return (
    <div
      className={`glass-card-hover p-5 space-y-3 ${
        task.status === 'completed' && onPreview ? 'cursor-pointer' : ''
      }`}
      onClick={handleClick}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <StatusBadge status={task.status} />
          <span className="text-sm text-gray-300 font-mono truncate">{task.source_filename}</span>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {onDelete && (
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              className="btn-ghost p-1.5 text-gray-500 hover:text-red-400"
              title="Supprimer"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
          <Link
            to={`/films/${task.film_id}`}
            className="btn-ghost flex-shrink-0"
            onClick={(e) => e.stopPropagation()}
          >
            <Eye className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* Film title */}
      {task.film_title && (
        <div className="text-xs text-gray-500 flex items-center gap-1.5">
          <ChevronRight className="w-3 h-3" />
          <span>{task.film_title}</span>
        </div>
      )}

      {(isRunning || task.status === 'completed') && (
        <TaskProgressBar status={task.status} progress={task.progress_pct} />
      )}

      {task.status === 'completed' && (
        <a
          href={`/api/tasks/${task.id}/download`}
          className="btn-primary w-full justify-center !py-2 !text-xs !bg-emerald-600 hover:!bg-emerald-500 !shadow-emerald-600/25"
          onClick={(e) => e.stopPropagation()}
        >
          <Download className="w-3.5 h-3.5" />
          Télécharger .srt
        </a>
      )}

      {/* Live button for pending/running tasks */}
      {isPendingOrRunning && (
        <Link
          to={`/tasks/${task.id}/live`}
          className="btn-secondary w-full justify-center !py-2 !text-xs !bg-brand-500/10 hover:!bg-brand-500/20 !border-brand-500/20 hover:!border-brand-500/30 !text-brand-300"
          onClick={(e) => e.stopPropagation()}
        >
          <Activity className="w-3.5 h-3.5" />
          Voir en direct
        </Link>
      )}

      {task.error_message && (
        <div className="text-xs text-red-400 bg-red-500/10 rounded-lg px-3 py-2 ring-1 ring-red-500/20">
          {task.error_message}
        </div>
      )}
    </div>
  );
}
