import { Upload, FileText } from 'lucide-react';
import { useRef, useState } from 'react';

interface Props {
  onUpload: (file: File) => void;
  disabled?: boolean;
}

/**
 * Detect source language from a subtitle filename.
 * Patterns: film.en.srt, film.en.sdh.srt, film.en-US.srt, film.srt
 */
function detectSourceLanguage(filename: string): string | null {
  // Match language code patterns in filename
  const match = filename.match(/[.\-_]([a-z]{2,3}(?:-[A-Z]{2,4})?)\.(?:srt|vtt|ass|ssa)$/i);
  if (match) return match[1].toLowerCase();
  // Also check for SDH pattern with language
  const sdhMatch = filename.match(/[.\-_]([a-z]{2,3})(?:\.sdh|\.hi|\.cc)?\./i);
  if (sdhMatch) return sdhMatch[1].toLowerCase();
  return null;
}

export default function SubtitleUploader({ onUpload, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleFile = (file: File) => {
    if (file) onUpload(file);
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
      }}
      className={`relative rounded-2xl p-8 text-center transition-all duration-300 cursor-pointer border-2 border-dashed ${
        dragging
          ? 'border-brand-400 bg-brand-500/10 scale-[1.01]'
          : 'border-white/[0.08] hover:border-white/[0.15] hover:bg-white/[0.02]'
      } ${disabled ? 'opacity-40 pointer-events-none' : ''}`}
      onClick={() => inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".srt,.vtt,.ass,.ssa"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          e.target.value = '';
        }}
      />

      <div className="flex flex-col items-center gap-3">
        <div className={`flex items-center justify-center w-14 h-14 rounded-2xl transition-all duration-300 ${
          dragging ? 'bg-brand-500/20' : 'bg-white/[0.04]'
        }`}>
          {dragging ? (
            <FileText className="w-7 h-7 text-brand-300" />
          ) : (
            <Upload className="w-7 h-7 text-gray-500" />
          )}
        </div>
        <div>
          <p className="text-sm text-gray-300 font-medium">
            {dragging ? 'Déposez le fichier ici' : 'Glisser-déposer ou cliquer'}
          </p>
          <p className="text-xs text-gray-600 mt-1">.srt · .vtt · .ass · .ssa — la langue sera détectée automatiquement</p>
        </div>
      </div>
    </div>
  );
}