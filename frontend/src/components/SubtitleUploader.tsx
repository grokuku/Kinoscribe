import { Upload } from 'lucide-react';
import { useRef, useState } from 'react';

interface Props {
  onUpload: (file: File, sourceLanguage: string) => void;
  disabled?: boolean;
}

export default function SubtitleUploader({ onUpload, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [sourceLang, setSourceLang] = useState('en');
  const [dragging, setDragging] = useState(false);

  const handleFile = (file: File) => {
    if (file) onUpload(file, sourceLang);
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
      className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer ${
        dragging
          ? 'border-brand-400 bg-brand-400/5'
          : 'border-gray-700 hover:border-gray-500'
      } ${disabled ? 'opacity-50 pointer-events-none' : ''}`}
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
          e.target.value = ''; // reset for re-upload
        }}
      />
      <Upload className="w-8 h-8 mx-auto mb-3 text-gray-500" />
      <p className="text-sm text-gray-400 mb-3">
        Glisser-déposer un fichier .srt / .vtt / .ass ici<br />
        ou cliquer pour sélectionner
      </p>
      <div className="flex items-center justify-center gap-2 text-sm">
        <label className="text-gray-500">Langue source :</label>
        <select
          value={sourceLang}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => setSourceLang(e.target.value)}
          className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-gray-200 text-sm focus:outline-none focus:border-brand-500"
        >
          {['en', 'es', 'de', 'it', 'pt', 'ja', 'ko', 'zh'].map((l) => (
            <option key={l} value={l}>{l.toUpperCase()}</option>
          ))}
        </select>
      </div>
    </div>
  );
}