import { Link } from 'react-router-dom';
import { useTasks } from '../hooks/useApi';
import { StatusBadge, TaskProgressBar } from '../components/TaskStatus';
import { Download, Eye, Activity, CheckCircle2, Clock, AlertCircle, Zap } from 'lucide-react';
import type { Task } from '../types';

export default function TasksPage() {
  const { data: tasks, loading, error, refresh } = useTasks();

  if (loading && !tasks) return (
    <div className="flex items-center justify-center py-32 text-gray-600">
      <div className="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
    </div>
  );
  if (error) return <div className="py-16 text-center text-red-400">Erreur : {error}</div>;

  const active = (tasks ?? []).filter((t) =>
    ['analyzing_context', 'translating', 'refining'].includes(t.status)
  );
  const completed = (tasks ?? []).filter((t) => t.status === 'completed');
  const pending = (tasks ?? []).filter((t) => t.status === 'pending');
  const failed = (tasks ?? []).filter((t) => t.status === 'failed');

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
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
          <StatCard icon={<Zap className="w-5 h-5 text-brand-400" />} value={active.length} label="En cours" color="brand" />
          <StatCard icon={<Clock className="w-5 h-5 text-gray-400" />} value={pending.length} label="En attente" color="gray" />
          <StatCard icon={<CheckCircle2 className="w-5 h-5 text-emerald-400" />} value={completed.length} label="Terminées" color="emerald" />
          <StatCard icon={<AlertCircle className="w-5 h-5 text-red-400" />} value={failed.length} label="Échouées" color="red" />
        </div>
      )}

      {/* Active */}
      {active.length > 0 && (
        <Section title="En cours" accent="brand">
          {active.map((t) => (
            <TaskCard key={t.id} task={t} />
          ))}
        </Section>
      )}

      {/* Pending */}
      {pending.length > 0 && (
        <Section title="En attente" accent="gray">
          {pending.map((t) => (
            <TaskCard key={t.id} task={t} />
          ))}
        </Section>
      )}

      {/* Failed */}
      {failed.length > 0 && (
        <Section title="Échouées" accent="red">
          {failed.map((t) => (
            <TaskCard key={t.id} task={t} />
          ))}
        </Section>
      )}

      {/* Completed */}
      {completed.length > 0 && (
        <Section title="Terminées" accent="emerald">
          {completed.map((t) => (
            <TaskCard key={t.id} task={t} />
          ))}
        </Section>
      )}
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

function Section({ title, accent, children }: { title: string; accent: string; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <div className="flex items-center gap-3 mb-4">
        <div className={`w-1 h-4 rounded-full bg-${accent}-500/60`} />
        <h2 className={`section-title !mb-0 text-${accent}-400/80`}>{title}</h2>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
        {children}
      </div>
    </div>
  );
}

function TaskCard({ task }: { task: Task }) {
  const isRunning = ['analyzing_context', 'translating', 'refining'].includes(task.status);

  return (
    <div className="glass-card-hover p-5 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <StatusBadge status={task.status} />
          <span className="text-sm text-gray-300 font-mono truncate">{task.source_filename}</span>
        </div>
        <Link
          to={`/films/${task.film_id}`}
          className="btn-ghost flex-shrink-0"
        >
          <Eye className="w-3.5 h-3.5" />
        </Link>
      </div>

      {(isRunning || task.status === 'completed') && (
        <TaskProgressBar status={task.status} progress={task.progress_pct} />
      )}

      {task.status === 'completed' && (
        <a
          href={`/api/tasks/${task.id}/download`}
          className="btn-primary w-full justify-center !py-2 !text-xs !bg-emerald-600 hover:!bg-emerald-500 !shadow-emerald-600/25"
        >
          <Download className="w-3.5 h-3.5" />
          Télécharger .srt
        </a>
      )}

      {task.error_message && (
        <div className="text-xs text-red-400 bg-red-500/10 rounded-lg px-3 py-2 ring-1 ring-red-500/20">
          {task.error_message}
        </div>
      )}
    </div>
  );
}