import { Link } from 'react-router-dom';
import { useTasks } from '../hooks/useApi';
import { StatusBadge, TaskProgressBar } from '../components/TaskStatus';
import { Download, Eye } from 'lucide-react';
import type { Task, TaskStatus } from '../types';

export default function TasksPage() {
  const { data: tasks, loading, error, refresh } = useTasks();

  if (loading && !tasks) return <div className="py-16 text-center text-gray-500">Chargement…</div>;
  if (error) return <div className="py-16 text-center text-red-400">Erreur : {error}</div>;

  const active = (tasks ?? []).filter((t) =>
    ['analyzing_context', 'translating', 'refining'].includes(t.status)
  );
  const completed = (tasks ?? []).filter((t) => t.status === 'completed');
  const others = (tasks ?? []).filter((t) =>
    ['pending', 'failed'].includes(t.status)
  );

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-100 mb-1">Tâches de traduction</h1>
      <p className="text-sm text-gray-500 mb-6">Suivez l'avancement de vos traductions</p>

      {tasks && tasks.length === 0 && (
        <div className="text-center py-20 text-gray-600">
          Aucune tâche. Uploadez un sous-titre depuis la page d'un film.
        </div>
      )}

      {/* Active */}
      {active.length > 0 && (
        <Section title="En cours">
          {active.map((t) => (
            <TaskCard key={t.id} task={t} />
          ))}
        </Section>
      )}

      {/* Pending / Failed */}
      {others.length > 0 && (
        <Section title="En attente / Échouées">
          {others.map((t) => (
            <TaskCard key={t.id} task={t} />
          ))}
        </Section>
      )}

      {/* Completed */}
      {completed.length > 0 && (
        <Section title="Terminées">
          {completed.map((t) => (
            <TaskCard key={t.id} task={t} />
          ))}
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">{title}</h2>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function TaskCard({ task }: { task: Task }) {
  const isRunning = ['analyzing_context', 'translating', 'refining'].includes(task.status);

  return (
    <div className="border border-gray-800 rounded-xl p-4 space-y-3 hover:border-gray-700 transition-colors">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <StatusBadge status={task.status} />
          <span className="text-sm text-gray-300 font-mono">{task.source_filename}</span>
          <Link
            to={`/films/${task.film_id}`}
            className="text-xs text-brand-400 hover:text-brand-300 flex items-center gap-1"
          >
            <Eye className="w-3 h-3" /> Voir le film
          </Link>
        </div>
        {task.status === 'completed' && (
          <a
            href={`/api/tasks/${task.id}/download`}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-md transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            Télécharger .srt
          </a>
        )}
      </div>

      {(isRunning || task.status === 'completed') && (
        <TaskProgressBar status={task.status} progress={task.progress_pct} />
      )}

      {task.error_message && (
        <p className="text-xs text-red-400 bg-red-900/20 rounded-md px-3 py-2">
          {task.error_message}
        </p>
      )}
    </div>
  );
}