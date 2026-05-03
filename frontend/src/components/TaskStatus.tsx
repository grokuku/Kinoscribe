import type { TaskStatus } from '../types';
import { CheckCircle2, Loader2, AlertCircle, Clock, Brain, Pen, Sparkles, Disc, Mic, RefreshCw, ArrowLeftRight } from 'lucide-react';

const statusConfig: Record<TaskStatus, { label: string; color: string; icon: typeof Clock; glow: string }> = {
  pending:            { label: 'En attente',         color: 'text-gray-400 bg-gray-500/10',     glow: '', icon: Clock },
  analyzing_context:  { label: 'Analyse du contexte', color: 'text-purple-300 bg-purple-500/10', glow: 'shadow-purple-500/20', icon: Brain },
  translating:        { label: 'Traduction',          color: 'text-blue-300 bg-blue-500/10',      glow: 'shadow-blue-500/20',  icon: Pen },
  refining:           { label: 'Affinage',           color: 'text-indigo-300 bg-indigo-500/10',   glow: 'shadow-indigo-500/20', icon: Sparkles },
  extracting:         { label: 'Extraction',         color: 'text-cyan-300 bg-cyan-500/10',       glow: 'shadow-cyan-500/20',   icon: Disc },
  transcribing:       { label: 'Transcription',      color: 'text-violet-300 bg-violet-500/10',   glow: 'shadow-violet-500/20', icon: Mic },
  syncing:            { label: 'Synchronisation',     color: 'text-amber-300 bg-amber-500/10',    glow: 'shadow-amber-500/20',  icon: ArrowLeftRight },
  rescanning:         { label: 'Rescan',              color: 'text-teal-300 bg-teal-500/10',      glow: 'shadow-teal-500/20',   icon: RefreshCw },
  completed:          { label: 'Terminé',             color: 'text-emerald-300 bg-emerald-500/10', glow: '', icon: CheckCircle2 },
  failed:             { label: 'Échoué',              color: 'text-red-300 bg-red-500/10',        glow: '', icon: AlertCircle },
};

export function StatusBadge({ status }: { status: TaskStatus }) {
  const cfg = statusConfig[status] ?? statusConfig.pending;
  const Icon = cfg.icon;
  return (
    <span className={`badge ${cfg.color} ${cfg.glow ? `shadow-sm ${cfg.glow}` : ''}`}>
      <Icon className="w-3.5 h-3.5" />
      {cfg.label}
    </span>
  );
}

export function TaskProgressBar({ status, progress }: { status: TaskStatus; progress: number }) {
  const cfg = statusConfig[status] ?? statusConfig.pending;
  const Icon = cfg.icon;
  const animated = !['completed', 'failed'].includes(status);

  const barColor = status === 'failed'
    ? 'bg-red-500'
    : status === 'completed'
      ? 'bg-emerald-500'
      : 'bg-gradient-to-r from-brand-500 to-violet-500';

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-2 font-medium text-gray-200">
          {animated && <Loader2 className="w-4 h-4 animate-spin text-brand-400" />}
          {!animated && <Icon className="w-4 h-4" />}
          {cfg.label}
        </span>
        <span className="text-gray-500 tabular-nums text-xs font-mono">{progress}%</span>
      </div>
      <div className="h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${barColor} ${animated ? 'animate-pulse' : ''}`}
          style={{ width: `${Math.max(progress, 2)}%` }}
        />
      </div>
    </div>
  );
}