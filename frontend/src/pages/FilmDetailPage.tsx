import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Trash2, Users, Languages, Play, Download,
  Film, Brain, BookOpen, FileText, ChevronRight, Mic, RefreshCw,
  Subtitles, Upload, Zap, MessageSquare, Disc, HardDriveDownload,
  Video, Clock, Sparkles, ArrowRightLeft, AlertCircle, Loader2, X, Check,
} from 'lucide-react';
import { useFilm, useTasks, useActiveTaskPolling } from '../hooks/useApi';
import { api } from '../api/client';
import { StatusBadge, TaskProgressBar } from '../components/TaskStatus';
import SubtitleUploader from '../components/SubtitleUploader';
import type { Task, TaskType, Character, GlossaryEntry, ExistingSubtitle, TrackInfo } from '../types';

// ─── Toast / Confirm system ──────────────────────────────────────────────

type ToastType = 'success' | 'error' | 'info';

interface Toast { id: number; type: ToastType; message: string; }

let toastId = 0;
const toastListeners: Set<(toasts: Toast[]) => void> = new Set();
let toastState: Toast[] = [];

function pushToast(type: ToastType, message: string) {
  const id = ++toastId;
  toastState = [...toastState, { id, type, message }];
  toastListeners.forEach(l => l([...toastState]));
  setTimeout(() => {
    toastState = toastState.filter(t => t.id !== id);
    toastListeners.forEach(l => l([...toastState]));
  }, 4000);
}

function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>(toastState);
  useEffect(() => {
    toastListeners.add(setToasts);
    return () => { toastListeners.delete(setToasts); };
  }, []);
  return toasts;
}

// Confirm dialog state
let resolveConfirm: ((value: boolean) => void) | null = null;
const confirmListeners: Set<(state: { open: boolean; message: string }) => void> = new Set();
let confirmState = { open: false, message: '' };

function showConfirm(message: string): Promise<boolean> {
  return new Promise(resolve => {
    resolveConfirm = resolve;
    confirmState = { open: true, message };
    confirmListeners.forEach(l => l({ ...confirmState }));
  });
}

function useConfirm() {
  const [state, setState] = useState(confirmState);
  useEffect(() => {
    confirmListeners.add(setState);
    return () => { confirmListeners.delete(setState); };
  }, []);

  const handleYes = () => {
    confirmState = { open: false, message: '' };
    confirmListeners.forEach(l => l({ ...confirmState }));
    resolveConfirm?.(true);
    resolveConfirm = null;
  };

  const handleNo = () => {
    confirmState = { open: false, message: '' };
    confirmListeners.forEach(l => l({ ...confirmState }));
    resolveConfirm?.(false);
    resolveConfirm = null;
  };

  return { ...state, handleYes, handleNo };
}

function ToastContainer() {
  const toasts = useToasts();
  if (toasts.length === 0) return null;
  return (
    <div className="fixed top-4 right-4 z-[100] space-y-2 max-w-sm">
      {toasts.map(t => (
        <div key={t.id} className={`flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium animate-slide-in-right ${
          t.type === 'error' ? 'bg-red-500/90 text-white' :
          t.type === 'success' ? 'bg-emerald-500/90 text-white' :
          'bg-brand-500/90 text-white'
        }`}>
          {t.type === 'error' && <AlertCircle className="w-4 h-4 shrink-0" />}
          {t.type === 'success' && <Check className="w-4 h-4 shrink-0" />}
          <span className="flex-1">{t.message}</span>
          <button onClick={() => {
            toastState = toastState.filter(x => x.id !== t.id);
            toastListeners.forEach(l => l([...toastState]));
          }} className="opacity-70 hover:opacity-100"><X className="w-3.5 h-3.5" /></button>
        </div>
      ))}
    </div>
  );
}

function ConfirmDialog() {
  const { open, message, handleYes, handleNo } = useConfirm();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[99] flex items-center justify-center bg-black/60">
      <div className="bg-gray-800 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl border border-white/10">
        <p className="text-white text-sm mb-6 whitespace-pre-line">{message}</p>
        <div className="flex gap-3 justify-end">
          <button onClick={handleNo} className="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition">Annuler</button>
          <button onClick={handleYes} className="px-4 py-2 text-sm rounded-lg bg-brand-500 text-white hover:bg-brand-600 transition">Confirmer</button>
        </div>
      </div>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────

const toast = {
  success: (msg: string) => pushToast('success', msg),
  error: (msg: string) => pushToast('error', msg),
  info: (msg: string) => pushToast('info', msg),
};

const confirm = showConfirm;

// ─── Types ────────────────────────────────────────────────────────────────

type Tab = 'profile' | 'translation';

const LANG_NAMES: Record<string, string> = {
  en: 'Anglais', fr: 'Français', es: 'Espagnol', de: 'Allemand',
  it: 'Italien', pt: 'Portugais', ja: 'Japonais', ko: 'Coréen', zh: 'Chinois',
  und: 'Inconnu',
};

const GENDER_COLORS: Record<string, string> = {
  male: 'bg-blue-500/15 text-blue-300',
  female: 'bg-pinka-500/15 text-pink-300',
  neutral: 'bg-amber-500/15 text-amber-300',
  unknown: 'bg-gray-500/15 text-gray-400',
};

const TASK_TYPE_LABELS: Record<string, string> = {
  translation: 'Traduction',
  improve: 'Amélioration',
  sync: 'Synchronisation',
  transcription: 'Transcription',
  extract_subs: 'Extraction sous-titres',
  extract_audio: 'Extraction audio',
  analyze: 'Analyse contextuelle',
};

export default function FilmDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: film, loading, error, refresh: refreshFilm } = useFilm(id!);
  const { tasks: polledTasks, hasActive } = useActiveTaskPolling(3000);
  const { data: staticTasks, refresh: refreshTasks } = useTasks();
  const filmTasks = (hasActive ? (polledTasks ?? []) : (staticTasks ?? []))
    .filter((t) => t.film_id === id);
  const [tab, setTab] = useState<Tab>('profile');
  const [uploading, setUploading] = useState(false);
  const [starting, setStarting] = useState<string | null>(null);
  const [glossary, setGlossary] = useState<GlossaryEntry[]>([]);
  const [lore, setLore] = useState<{ lore_summary: string | null; task_id: string | null; task_status: string | null } | null>(null);
  const [subtitles, setSubtitles] = useState<ExistingSubtitle[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [whisperModel, setWhisperModel] = useState('medium');
  const [tracks, setTracks] = useState<{ audio: TrackInfo[]; subtitle: TrackInfo[]; video: TrackInfo[] } | null>(null);
  const [loadingTracks, setLoadingTracks] = useState(false);
  const [extractingTracks, setExtractingTracks] = useState(false);
  const [installing, setInstalling] = useState<string | null>(null);
  const [rescanning, setRescanning] = useState(false);
  const [enriching, setEnriching] = useState(false);

  useEffect(() => {
    if (id) {
      api.getFilmGlossary(id).then(setGlossary).catch(() => {});
      api.getFilmLore(id).then(setLore).catch(() => {});
      api.getFilmSubtitles(id).then(setSubtitles).catch(() => {});
    }
  }, [id, filmTasks?.length]);

  useEffect(() => {
    if (film?.analysis_status === 'analyzing') {
      const timer = setInterval(() => refreshFilm(), 3000);
      return () => clearInterval(timer);
    }
  }, [film?.analysis_status, refreshFilm]);

  useEffect(() => {
    if (film?.analysis_status === 'idle' && lore?.lore_summary === null) {
      api.getFilmLore(id!).then(setLore).catch(() => {});
      api.getFilmGlossary(id!).then(setGlossary).catch(() => {});
    }
  }, [film?.analysis_status]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      await api.uploadSubtitle(film!.id, file);
      refreshTasks(); refreshFilm();
      api.getFilmSubtitles(id!).then(setSubtitles).catch(() => {});
      toast.success('Sous-titre uploadé');
    } catch (e: any) { toast.error('Upload erreur : ' + e.message); }
    finally { setUploading(false); }
  };

  const handleStart = async (taskId: string) => {
    setStarting(taskId);
    try {
      await api.startTranslation(taskId);
      refreshTasks();
      toast.info('Traduction lancée');
    } catch (e: any) { toast.error('Démarrage erreur : ' + e.message); }
    finally { setStarting(null); }
  };

  const handleTranslateExisting = async (sub: ExistingSubtitle) => {
    const label = LANG_NAMES[sub.language || 'und'] || sub.language;
    if (!await confirm(`Traduire "${sub.filename}" (${label}) ?`)) return;
    setStarting('existing');
    try {
      const task = await api.translateExistingSubtitle(film!.id, sub.path, sub.language || undefined);
      await api.startTranslation(task.id);
      refreshTasks();
      toast.info('Traduction lancée');
    } catch (e: any) { toast.error('Erreur : ' + e.message); }
    finally { setStarting(null); }
  };

  const handleImproveExisting = async (sub: ExistingSubtitle) => {
    setStarting('existing');
    try {
      const task = await api.translateExistingSubtitle(film!.id, sub.path, sub.language || undefined, 'improve');
      await api.startTranslation(task.id);
      refreshTasks();
      toast.info('Amélioration lancée');
    } catch (e: any) { toast.error('Erreur : ' + e.message); }
    finally { setStarting(null); }
  };

  const handleAnalyze = async () => {
    setAnalyzing(true);
    try {
      await api.analyzeFilm(film!.id);
      refreshFilm();
      toast.info('Analyse contextuelle lancée');
    } catch (e: any) { toast.error('Erreur analyse : ' + e.message); }
    finally { setAnalyzing(false); }
  };

  const handleRescan = async () => {
    if (!await confirm('Rescanner ce film ? Les métadonnées seront mises à jour à partir du dossier source.')) return;
    setRescanning(true);
    try {
      await api.rescanFilm(film!.id);
      toast.info('Rescan lancé en arrière-plan');
      setTimeout(() => refreshFilm(), 3000);
    } catch (e: any) { toast.error('Erreur : ' + e.message); }
    finally { setRescanning(false); }
  };

  const handleEnrich = async () => {
    setEnriching(true);
    try {
      const result = await api.enrichFilm(film!.id);
      if (result.fields_updated) {
        refreshFilm();
        toast.success(`Métadonnées enrichies depuis ${result.source === 'tmdb' ? 'TMDB' : 'IMDb'} !`);
      } else {
        toast.info('Aucune nouvelle métadonnée trouvée.');
      }
    } catch (e: any) { toast.error('Erreur enrichissement : ' + e.message); }
    finally { setEnriching(false); }
  };

  const handleTranscribe = async () => {
    if (!await confirm(`Lancer la transcription Whisper (${whisperModel}) ?\nCela peut prendre du temps sur CPU.`)) return;
    setTranscribing(true);
    try {
      await api.transcribeFilm(film!.id, whisperModel);
      toast.info('Transcription Whisper lancée en arrière-plan');
    } catch (e: any) { toast.error('Erreur : ' + e.message); }
    finally { setTranscribing(false); }
  };

  const handleSync = async (sub: ExistingSubtitle) => {
    if (!await confirm(`Créer une tâche de synchronisation pour "${sub.filename}" ?`)) return;
    setStarting('existing');
    try {
      const task = await api.translateExistingSubtitle(film!.id, sub.path, sub.language || undefined, 'sync');
      await api.startTranslation(task.id);
      refreshTasks();
      toast.info('Synchronisation lancée');
    } catch (e: any) { toast.error('Erreur : ' + e.message); }
    finally { setStarting(null); }
  };

  const handleLoadTracks = async () => {
    if (!film?.video_path) { toast.error('Aucun fichier vidéo trouvé.'); return; }
    setLoadingTracks(true);
    try {
      const result = await api.getFilmTracks(film.id);
      setTracks({ audio: result.audio || [], subtitle: result.subtitle || [], video: result.video || [] });
    } catch (e: any) { toast.error('Erreur pistes : ' + e.message); }
    finally { setLoadingTracks(false); }
  };

  const handleExtractSubs = async () => {
    setExtractingTracks(true);
    try {
      const result = await api.extractSubtitles(film!.id);
      if (result.message) { toast.info(result.message); }
      else { toast.success(`${result.tracks?.length || 0} piste(s) extraite(s)`); }
      api.getFilmSubtitles(id!).then(setSubtitles).catch(() => {});
    } catch (e: any) { toast.error('Extraction erreur : ' + e.message); }
    finally { setExtractingTracks(false); }
  };

  const handleCleanWork = async () => {
    if (!await confirm('Supprimer tous les fichiers de travail ?\nLe dossier source du film ne sera pas modifié.')) return;
    try {
      await api.cleanWorkFiles(film!.id);
      toast.success('Fichiers de travail nettoyés');
    } catch (e: any) { toast.error('Nettoyage erreur : ' + e.message); }
  };

  const handleInstall = async (taskId: string) => {
    if (!await confirm('Installer le sous-titre traduit dans le dossier source du film ?')) return;
    setInstalling(taskId);
    try {
      const result = await api.installSubtitle(taskId);
      toast.success(`Sous-titre installé : ${result.destination}`);
    } catch (e: any) { toast.error('Installation erreur : ' + e.message); }
    finally { setInstalling(null); }
  };

  const handleDelete = async () => {
    if (!await confirm('Supprimer ce film ?')) return;
    await api.deleteFilm(film!.id);
    navigate('/');
  };

  // ─── Render ────────────────────────────────────────────────────────────

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 animate-spin text-brand-400" /></div>;
  if (error || !film) return <div className="text-red-400 text-center py-12">Film introuvable</div>;

  const isAnalyzing = film.analysis_status === 'analyzing';

  return (
    <>
      <ToastContainer />
      <ConfirmDialog />
      <div className="page-container">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <Link to="/" className="btn-ghost !p-2"><ArrowLeft className="w-4 h-4" /></Link>
          <div className="flex-1 min-w-0">
            <h1 className="text-xl font-bold truncate">{film.title}</h1>
            {film.year && <span className="text-sm text-gray-500">{film.year}</span>}
            {film.director && <span className="text-sm text-gray-500 ml-2">· de {film.director}</span>}
          </div>
          <button onClick={handleAnalyze} disabled={analyzing || isAnalyzing} className="btn-secondary !text-xs" title="Analyse contextuelle">
            {analyzing || isAnalyzing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Brain className="w-3.5 h-3.5" />}
            {analyzing || isAnalyzing ? 'Analyse…' : 'Analyser'}
          </button>
          <button onClick={handleRescan} disabled={rescanning} className="btn-ghost !p-2 text-gray-600 hover:text-brand-400" title="Rescanner le film">
            <RefreshCw className={`w-4 h-4 ${rescanning ? 'animate-spin' : ''}`} />
          </button>
          <button onClick={handleDelete} className="btn-ghost !p-2 text-gray-600 hover:text-red-400" title="Supprimer"><Trash2 className="w-4 h-4" /></button>
        </div>

        {/* Tab selector */}
        <div className="flex gap-1 mb-6 bg-gray-900/50 rounded-lg p-1 w-fit">
          <button onClick={() => setTab('profile')} className={`tab-btn ${tab === 'profile' ? 'active' : ''}`}>
            <BookOpen className="w-3.5 h-3.5" /> Profil
          </button>
          <button onClick={() => setTab('translation')} className={`tab-btn ${tab === 'translation' ? 'active' : ''}`}>
            <Languages className="w-3.5 h-3.5" /> Traduction
          </button>
        </div>

        {/* Active tasks */}
        {filmTasks.length > 0 && (
          <div className="mb-6 space-y-2">
            {filmTasks.map(task => (
              <div key={task.id} className="flex items-center gap-3 bg-gray-800/60 rounded-lg px-4 py-2.5">
                <StatusBadge status={task.status} />
                <span className="text-sm text-gray-300 flex-1">
                  {task.source_filename}
                  {task.task_type && task.task_type !== 'translation' && (
                    <span className="ml-2 text-xs text-brand-400">({TASK_TYPE_LABELS[task.task_type] || task.task_type})</span>
                  )}
                </span>
                <TaskProgressBar status={task.status} progress={task.progress_pct} />
                {task.status === 'completed' && task.target_path && (
                  <button onClick={() => handleInstall(task.id)} disabled={installing === task.id} className="btn-secondary !text-xs">
                    <HardDriveDownload className="w-3 h-3" /> Installer
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {tab === 'profile' ? (
          <ProfileTab
            film={film} glossary={glossary} lore={lore} characters={film.characters}
            onAnalyze={handleAnalyze} analyzing={analyzing || isAnalyzing}
            onEnrich={handleEnrich} enriching={enriching}
          />
        ) : (
          <TranslationTab
            film={film} subtitles={subtitles}
            onUpload={handleUpload} uploading={uploading}
            onTranslateExisting={handleTranslateExisting}
            onImproveExisting={handleImproveExisting}
            onSync={handleSync} whisperModel={whisperModel} setWhisperModel={setWhisperModel}
            onAnalyze={handleAnalyze} analyzing={analyzing || isAnalyzing}
            tracks={tracks} loadingTracks={loadingTracks} extractingTracks={extractingTracks}
            onLoadTracks={handleLoadTracks} onExtractSubs={handleExtractSubs}
            onTranscribe={handleTranscribe} transcribing={transcribing}
            onCleanWork={handleCleanWork}
          />
        )}
      </div>
    </>
  );
}

// ─── Profile Tab ────────────────────────────────────────────────────────────

function ProfileTab({ film, glossary, lore, characters, onAnalyze, analyzing, onEnrich, enriching }: {
  film: any; glossary: GlossaryEntry[]; lore: any; characters: Character[];
  onAnalyze: () => void; analyzing: boolean; onEnrich: () => void; enriching: boolean;
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Sidebar metadata */}
      <div className="space-y-4">
        <h2 className="section-title">Métadonnées</h2>
        <button onClick={onEnrich} disabled={enriching} className="btn-secondary w-full !text-xs mb-2">
          {enriching ? <Loader2 className="w-3 h-3 animate-spin" /> : <Film className="w-3 h-3" />} Enrichir depuis IMDb
        </button>
        <MetaCard label="Langue source" value={LANG_NAMES[film.source_language] || film.source_language.toUpperCase()} />
        <MetaCard label="Langue cible" value={LANG_NAMES[film.target_language] || film.target_language.toUpperCase()} />
        {film.director && <MetaCard label="Réalisateur" value={film.director} />}
        {film.year && <MetaCard label="Année" value={String(film.year)} />}
        {film.genre && <MetaCard label="Genre" value={film.genre} />}
        {film.studio && <MetaCard label="Studio" value={film.studio} />}
        {film.rating && <MetaCard label="Note" value={`⭐ ${film.rating}/10`} />}
        {film.imdb_id && <MetaCard label="IMDb" value={film.imdb_id} mono />}
        {film.imdb_id && <a href={`https://www.imdb.com/title/${film.imdb_id}`} target="_blank" rel="noopener noreferrer" className="block text-xs text-brand-400 hover:underline mt-1 mb-2">Voir sur IMDb ↗</a>}
        {film.tmdb_id && <MetaCard label="TMDB" value={film.tmdb_id} mono />}
        {film.path && <MetaCard label="Dossier" value={film.path} mono />}
        {film.video_path && <MetaCard label="Vidéo" value={film.video_path.split('/').pop() || film.video_path} mono />}
        {film.poster_path && <MetaCard label="Poster" value="✅ Disponible" />}
        <MetaCard label="Sous-titres existants" value={film.has_existing_subs ? '✅ Oui' : '❌ Non'} />
        <MetaCard label="Analyse" value={
          analyzing ? '🔄 En cours…' :
          film.analysis_status === 'failed' ? '❌ Échouée' :
          film.lore_summary ? '✅ Terminée' : '—'
        } />
      </div>

      {/* Lore */}
      <div className="lg:col-span-2 space-y-6">
        {film.summary && (
          <div>
            <h2 className="section-title">Résumé</h2>
            <p className="text-sm text-gray-300 whitespace-pre-line">{film.summary}</p>
          </div>
        )}
        {lore?.lore_summary && (
          <div>
            <h2 className="section-title">Contexte narratif</h2>
            <p className="text-sm text-gray-300 whitespace-pre-line">{lore.lore_summary}</p>
          </div>
        )}

        {/* Characters */}
        {characters.length > 0 && (
          <div>
            <h2 className="section-title">Personnages ({characters.length})</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {characters.map(c => (
                <div key={c.id || c.name} className="flex items-center gap-2 bg-gray-800/40 rounded-lg px-3 py-2">
                  <span className={`w-2 h-2 rounded-full ${GENDER_COLORS[c.gender || 'unknown']?.split(' ')[0]}`} />
                  <span className="text-sm font-medium text-gray-200">{c.name}</span>
                  {c.description && <span className="text-xs text-gray-500 ml-auto">{c.description}</span>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Glossary */}
        {glossary.length > 0 && (
          <div>
            <h2 className="section-title">Glossaire ({glossary.length})</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {glossary.map(g => (
                <div key={g.id || g.source_term} className="bg-gray-800/40 rounded-lg px-3 py-2">
                  <span className="text-sm text-white">{g.source_term}</span>
                  <span className="text-xs text-gray-500 mx-2">→</span>
                  <span className="text-sm text-emerald-400">{g.target_term}</span>
                  {g.notes && <p className="text-xs text-gray-500 mt-0.5">{g.notes}</p>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Translation Tab ──────────────────────────────────────────────────────

function TranslationTab({ film, subtitles, onUpload, uploading, onTranslateExisting, onImproveExisting, onSync, whisperModel, setWhisperModel, onAnalyze, analyzing, tracks, loadingTracks, extractingTracks, onLoadTracks, onExtractSubs, onTranscribe, transcribing, onCleanWork }: {
  film: any; subtitles: ExistingSubtitle[];
  onUpload: (file: File) => void; uploading: boolean;
  onTranslateExisting: (sub: ExistingSubtitle) => void;
  onImproveExisting: (sub: ExistingSubtitle) => void;
  onSync: (sub: ExistingSubtitle) => void; whisperModel: string; setWhisperModel: (m: string) => void;
  onAnalyze: () => void; analyzing: boolean;
  tracks: any; loadingTracks: boolean; extractingTracks: boolean;
  onLoadTracks: () => void; onExtractSubs: () => void;
  onTranscribe: () => void; transcribing: boolean;
  onCleanWork: () => void;
}) {
  const isFRExisting = (sub: ExistingSubtitle) => (sub.language || '').toLowerCase().startsWith('fr');
  return (
    <div className="space-y-6">
      {/* Upload */}
      <div>
        <h2 className="section-title mb-3">Sous-titres disponibles</h2>
        <SubtitleUploader onUpload={onUpload} disabled={uploading} />
      </div>

      {/* Existing subtitles */}
      {subtitles.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-400 mb-2">Fichiers trouvés ({subtitles.length})</h3>
          <div className="space-y-2">
            {subtitles.map(sub => (
              <SubtitleCard key={sub.path} sub={sub} onTranslate={onTranslateExisting} onImprove={onImproveExisting} onSync={onSync} isFR={isFRExisting(sub)} />
            ))}
          </div>
        </div>
      )}

      {/* Tracks */}
      <div>
        <div className="flex items-center gap-3 mb-3">
          <h2 className="section-title !mb-0">Pistes embarquées</h2>
          <button onClick={onLoadTracks} disabled={loadingTracks} className="btn-secondary !text-xs">
            {loadingTracks ? <Loader2 className="w-3 h-3 animate-spin" /> : <Disc className="w-3 h-3" />} Analyser
          </button>
        </div>
        {tracks && (
          <div className="space-y-3">
            {tracks.subtitle.length > 0 && (
              <div>
                <h4 className="text-xs text-gray-500 mb-1">Sous-titres</h4>
                {tracks.subtitle.map((t: TrackInfo, i: number) => (
                  <div key={i} className="text-sm text-gray-300 flex items-center gap-2">
                    <span className="text-xs bg-gray-700 px-1.5 py-0.5 rounded">{t.codec}</span>
                    <span>{t.language || 'und'}</span>
                    {t.title && <span className="text-gray-500 text-xs">({t.title})</span>}
                  </div>
                ))}
                <button onClick={onExtractSubs} disabled={extractingTracks} className="btn-secondary !text-xs mt-2">
                  {extractingTracks ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />} Extraire les sous-titres
                </button>
              </div>
            )}
            {tracks.audio.length > 0 && (
              <div>
                <h4 className="text-xs text-gray-500 mb-1">Audio</h4>
                {tracks.audio.map((t: TrackInfo, i: number) => (
                  <div key={i} className="text-sm text-gray-300 flex items-center gap-2">
                    <span className="text-xs bg-gray-700 px-1.5 py-0.5 rounded">{t.codec}</span>
                    <span>{t.language || 'und'}</span>
                    {t.channels && <span className="text-xs text-gray-500">{t.channels}ch</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Whisper transcription */}
      <div>
        <h2 className="section-title mb-3">Transcription Whisper</h2>
        <div className="flex items-center gap-3">
          <select value={whisperModel} onChange={e => setWhisperModel(e.target.value)} className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm">
            <option value="tiny">Tiny (rapide)</option>
            <option value="base">Base</option>
            <option value="small">Small</option>
            <option value="medium">Medium</option>
            <option value="large">Large (lent)</option>
          </select>
          <button onClick={onTranscribe} disabled={transcribing} className="btn-primary !text-xs">
            {transcribing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Mic className="w-3 h-3" />} Lancer
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-2">Génère des sous-titres à partir de l'audio. Nécessite faster-whisper.</p>
      </div>

      {/* Work files */}
      <div>
        <div className="flex items-center gap-3">
          <h2 className="section-title !mb-0">Fichiers de travail</h2>
          <button onClick={onCleanWork} className="btn-ghost !text-xs text-red-400 hover:text-red-300">
            <Trash2 className="w-3 h-3" /> Nettoyer
          </button>
        </div>
      </div>

      {/* Video player */}
      {film.video_path && (
        <div>
          <h2 className="section-title mb-3">Lecteur vidéo</h2>
          <video controls className="w-full rounded-lg bg-black" style={{ maxHeight: '40vh' }}>
            <source src={api.getFilmVideoUrl(film.id)} type="video/mp4" />
            Votre navigateur ne supporte pas la lecture vidéo.
          </video>
          <p className="text-xs text-gray-500 mt-1">Lecteur local — ne fonctionne pas pour les sources SSH.</p>
        </div>
      )}
    </div>
  );
}

// ─── SubtitleCard ────────────────────────────────────────────────────────

function SubtitleCard({ sub, onTranslate, onImprove, onSync, isFR }: {
  sub: ExistingSubtitle; onTranslate: (s: ExistingSubtitle) => void;
  onImprove: (s: ExistingSubtitle) => void; onSync: (s: ExistingSubtitle) => void;
  isFR: boolean;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const label = LANG_NAMES[sub.language || 'und'] || sub.language;
  return (
    <div className="flex items-center gap-3 bg-gray-800/40 rounded-lg px-3 py-2 group">
      <FileText className="w-4 h-4 text-gray-400 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-200 truncate">{sub.filename}</p>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span>{label}</span>
          <span>·</span>
          <span>{sub.format}</span>
          {sub.is_sdh && <span className="bg-yellow-500/20 text-yellow-300 px-1 rounded">SDH</span>}
          {sub.source !== 'scanner' && <span className="text-brand-400">{sub.source}</span>}
        </div>
      </div>
      <div className="relative">
        <button onClick={() => setMenuOpen(!menuOpen)} className="btn-ghost !p-1 text-xs opacity-0 group-hover:opacity-100 transition">
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
        {menuOpen && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
            <div className="absolute right-0 top-8 z-20 bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[200px]">
              <button className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/5 flex items-center gap-2" onClick={() => { onTranslate(sub); setMenuOpen(false); }}>
                <Languages className="w-3.5 h-3.5" /> Traduire
              </button>
              <button className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/5 flex items-center gap-2" onClick={() => { onImprove(sub); setMenuOpen(false); }}>
                <Sparkles className="w-3.5 h-3.5 text-violet-400" /> Améliorer
              </button>
              <button className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/5 flex items-center gap-2" onClick={() => { onSync(sub); setMenuOpen(false); }}>
                <Clock className="w-3.5 h-3.5" /> Resynchroniser
              </button>
              {isFR && (
                <button className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/5 flex items-center gap-2" onClick={() => { onTranslate(sub); setMenuOpen(false); }}>
                  <ArrowRightLeft className="w-3.5 h-3.5" /> Refaire entièrement
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── MetaCard ──────────────────────────────────────────────────────────────

function MetaCard({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-gray-800/50">
      <span className="text-xs text-gray-500">{label}</span>
      <span className={`text-sm ${mono ? 'font-mono text-xs' : 'text-gray-200'} truncate ml-4 text-right`}>{value}</span>
    </div>
  );
}