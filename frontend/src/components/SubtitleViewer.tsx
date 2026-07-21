import { useRef, useEffect, useState } from 'react';
import type { SubtitleLine } from '../types';
import { Loader2 } from 'lucide-react';

interface SubtitleViewerProps {
  lines: SubtitleLine[];
  loading?: boolean;
}

export default function SubtitleViewer({ lines, loading = false }: SubtitleViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [previousCount, setPreviousCount] = useState(0);
  const [newIndices, setNewIndices] = useState<Set<number>>(new Set());

  // Detect new lines by comparing array length
  useEffect(() => {
    if (lines.length > previousCount) {
      // Mark newly arrived lines (from previousCount to current length)
      const newSet = new Set<number>();
      for (let i = previousCount; i < lines.length; i++) {
        newSet.add(lines[i].index);
      }
      setNewIndices(newSet);
      setPreviousCount(lines.length);

      // Clear the highlight after animation completes
      const timer = setTimeout(() => setNewIndices(new Set()), 2000);
      return () => clearTimeout(timer);
    } else if (lines.length < previousCount) {
      // Reset if lines are reset (e.g., new task)
      setPreviousCount(lines.length);
    }
  }, [lines, previousCount]);

  // Auto-scroll to bottom when new lines arrive
  useEffect(() => {
    if (containerRef.current && lines.length > 0) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [lines.length]);

  return (
    <div className="glass-card overflow-hidden flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
        <h3 className="text-sm font-semibold text-gray-200">
          Sous-titres traduits
        </h3>
        <div className="flex items-center gap-2">
          {loading && (
            <span className="flex items-center gap-1.5 text-xs text-brand-400">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Mise à jour...
            </span>
          )}
          <span className="text-xs text-gray-500 font-mono">
            {lines.length} ligne{lines.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* Lines container */}
      <div
        ref={containerRef}
        className="overflow-y-auto flex-1 max-h-[60vh] min-h-[300px] scroll-smooth"
      >
        {lines.length === 0 && !loading && (
          <div className="flex items-center justify-center h-full py-16 text-center">
            <p className="text-sm text-gray-500">
              Aucune ligne de sous-titre pour le moment.<br />
              La traduction va débuter...
            </p>
          </div>
        )}

        {lines.length === 0 && loading && (
          <div className="flex items-center justify-center h-full py-16">
            <Loader2 className="w-8 h-8 text-brand-400 animate-spin" />
          </div>
        )}

        <div className="divide-y divide-white/[0.04]">
          {lines.map((line) => {
            const isNew = newIndices.has(line.index);
            return (
              <SubtitleLineRow
                key={line.index}
                line={line}
                isNew={isNew}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

function SubtitleLineRow({ line, isNew }: { line: SubtitleLine; isNew: boolean }) {
  return (
    <div
      className={`flex gap-3 px-5 py-2.5 transition-all duration-1000 ${
        isNew
          ? 'bg-emerald-500/10 border-l-2 border-emerald-400/60'
          : 'bg-transparent border-l-2 border-transparent hover:bg-white/[0.02]'
      }`}
    >
      {/* Index */}
      <span className="text-gray-500 w-8 text-right flex-shrink-0 select-none text-xs leading-5 font-mono">
        {line.index}
      </span>

      {/* Timestamp */}
      <span className="text-gray-600 w-40 flex-shrink-0 font-mono text-xs leading-5 select-none">
        {line.start} <span className="text-gray-700">→</span> {line.end}
      </span>

      {/* Text */}
      <span className="text-gray-200 break-words leading-5 text-sm">
        {line.text}
      </span>
    </div>
  );
}
