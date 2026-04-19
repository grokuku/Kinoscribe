import type { TaskStatus } from '../types';
import { CheckCircle2, Loader2, AlertCircle, Clock, Brain, Pen, Sparkles } from 'lucide-react';

const statusConfig: Record<TaskStatus, { label: string; color: string; icon: typeof Clock }> = {
  pending:            { label: 'En attente',         color: 'text-gray-400 bg-gray-800',    icon: Clock },
  analyzing_context:  { label: 'Analyse du contexte', color: 'text-purple-400 bg-purple-900/40', icon: Brain },
  translating:        { label: 'Traduction',          color: 'text-blue-400 bg-blue-900/40',     icon: Pen },
  refining:           { label: 'Affinage',           color: 'text-indigo-400 bg-indigo-900/40',  icon: Sparkles },
  completed:          { label: 'Terminé',             color: 'text-emerald-400 bg-emerald-900/40', icon: CheckCircle2 },
  failed:             { label: 'Échoué',              color: 'text-red-400 bg-red-900/40',        icon: AlertCircle },
};

export function StatusBadge({ status }: { status: TaskStatus }) {
  const cfg = statusConfig[status] ?? statusConfig.pending;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
      <Icon className="w-3.5 h-3.5" />
      {cfg.label}
    </span>
  );
}

export function TaskProgressBar({ status, progress }: { status: TaskStatus; progress: number }) {
  const cfg = statusConfig[status] ?? statusConfig.pending;
  const Icon = cfg.icon;
  const animated = !['completed', 'failed'].includes(status);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-1.5 font-medium text-gray-200">
          {animated && <Loader2 className="w-4 h-4 animate-spin" />}
          {!animated && <Icon className="w-4 h-4" />}
          {cfg.label}
        </span>
        <span className="text-gray-500 tabular-nums">{progress}%</span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${
            status === 'failed' ? 'bg-red-500' : status === 'completed' ? 'bg-emerald-500' : 'bg-brand-500'
          } ${animated ? 'animate-pulse' : ''}`}
          style={{ width: `${Math.max(progress, 2)}%` }}
        />
      </div>
    </div>
  );
}