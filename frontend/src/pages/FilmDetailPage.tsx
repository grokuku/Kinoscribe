import { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Trash2, Languages, Download,
  Film, Brain, FileText, ChevronDown, Mic, RefreshCw,
  Sparkles, ArrowRightLeft, AlertCircle, Loader2, X, Check,
  HardDriveDownload, Disc, Clock, Play, Eye,
} from 'lucide-react';
import { useFilm, useTasks, useActiveTaskPolling, useTaskContent } from '../hooks/useApi';
import { api } from '../api/client';
import { StatusBadge, TaskProgressBar } from '../components/TaskStatus';
import SubtitleUploader from '../components/SubtitleUploader';
import SubtitleViewer from '../components/SubtitleViewer';
import type { Task, Character, GlossaryEntry, ExistingSubtitle, TrackInfo, TranslationVersion, SubtitleLine } from '../types';

// ─── Toast / Confirm system ──────────────────────────────────────────────

type ToastType = 'success' | 'error' | 'info';
interface Toast { id: number; type: ToastType; message: string; }
let toastId = 0;
const toastListeners: Set<(t: Toast[]) => void> = new Set();
let toastState: Toast[] = [];
function pushToast(type: ToastType, message: string) {
  const id = ++toastId;
  toastState = [...toastState, { id, type, message }];
  toastListeners.forEach(l => l([...toastState]));
  setTimeout(() => { toastState = toastState.filter(t => t.id !== id); toastListeners.forEach(l => l([...toastState])); }, 4000);
}
function useToasts() {
  const [t, setT] = useState(toastState);
  useEffect(() => { toastListeners.add(setT); return () => { toastListeners.delete(setT); }; }, []);
  return t;
}
let resolveConfirm: ((v: boolean) => void) | null = null;
const confirmListeners: Set<(s: { open: boolean; message: string }) => void> = new Set();
let confirmState = { open: false, message: '' };
function showConfirm(msg: string): Promise<boolean> {
  return new Promise(r => { resolveConfirm = r; confirmState = { open: true, message: msg }; confirmListeners.forEach(l => l({ ...confirmState })); });
}
function useConfirm() {
  const [s, setS] = useState(confirmState);
  useEffect(() => { confirmListeners.add(setS); return () => { confirmListeners.delete(setS); }; }, []);
  const yes = () => { confirmState = { open: false, message: '' }; confirmListeners.forEach(l => l({ ...confirmState })); resolveConfirm?.(true); resolveConfirm = null; };
  const no = () => { confirmState = { open: false, message: '' }; confirmListeners.forEach(l => l({ ...confirmState })); resolveConfirm?.(false); resolveConfirm = null; };
  return { ...s, yes, no };
}
const toast = { success: (m: string) => pushToast('success', m), error: (m: string) => pushToast('error', m), info: (m: string) => pushToast('info', m) };
const confirm = showConfirm;

// ─── Constants ──────────────────────────────────────────────────────────

const LANG_NAMES: Record<string, string> = {
  en: 'Anglais', fr: 'Français', es: 'Espagnol', de: 'Allemand',
  it: 'Italien', pt: 'Portugais', ja: 'Japonais', ko: 'Coréen', zh: 'Chinois', und: 'Inconnu',
};
const GENDER_COLORS: Record<string, string> = {
  male: 'bg-blue-500/15 text-blue-300', female: 'bg-pink-500/15 text-pink-300',
  neutral: 'bg-amber-500/15 text-amber-300', unknown: 'bg-gray-500/15 text-gray-400',
};
const TASK_TYPE_LABELS: Record<string, string> = {
  translation: 'Traduction', improve: 'Amélioration', sync: 'Synchronisation',
  transcription: 'Transcription', extract_subs: 'Extraction sous-titres',
  extract_audio: 'Extraction audio', analyze: 'Analyse contextuelle',
  pipeline: 'Pipeline complet',
};

// ─── Main Page ───────────────────────────────────────────────────────────

export default function FilmDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: film, loading, error, refresh: refreshFilm } = useFilm(id!);
  const { tasks: polledTasks, hasActive } = useActiveTaskPolling(3000);
  const { data: staticTasks, refresh: refreshTasks } = useTasks();
  const filmTasks = (polledTasks ?? staticTasks ?? []).filter(t => t.film_id === id);

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
  const [translations, setTranslations] = useState<TranslationVersion[]>([]);
  // ── Preview modal state ──
  const [previewTaskId, setPreviewTaskId] = useState<string | null>(null);
  const [previewVersionPath, setPreviewVersionPath] = useState<string | null>(null);
  const [previewVersionContent, setPreviewVersionContent] = useState<SubtitleLine[] | null>(null);
  const [previewVersionLoading, setPreviewVersionLoading] = useState(false);
  const { data: taskContentLines, loading: taskContentLoading } = useTaskContent(previewTaskId);
  const [open, setOpen] = useState<Record<string, boolean>>({ subs: true, tracks: false, whisper: false, video: false, pipeline: false, translations: false });
  const [pipelineDialog, setPipelineDialog] = useState(false);
  const [pipelineSteps, setPipelineSteps] = useState({ extract: true, transcribe: true, analyze: true, translate: true, install: true });

  const toggle = (key: string) => setOpen(p => ({ ...p, [key]: !p[key] }));

  useEffect(() => {
    if (id) {
      api.getFilmGlossary(id).then(setGlossary).catch(() => {});
      api.getFilmLore(id).then(setLore).catch(() => {});
      api.getFilmSubtitles(id).then(setSubtitles).catch(() => {});
      api.listTranslations(id).then(r => setTranslations(r.versions)).catch(() => {});
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

  // ─── Handlers ────────────────────────────────────────────────────────
  const handleUpload = async (file: File) => {
    setUploading(true);
    try { await api.uploadSubtitle(film!.id, file); refreshTasks(); refreshFilm(); api.getFilmSubtitles(id!).then(setSubtitles).catch(() => {}); toast.success('Sous-titre uploadé'); }
    catch (e: any) { toast.error('Upload erreur : ' + e.message); } finally { setUploading(false); }
  };

  const handleStart = async (taskId: string) => {
    setStarting(taskId);
    try { await api.startTranslation(taskId); refreshTasks(); toast.info('Traduction lancée'); }
    catch (e: any) { toast.error('Erreur : ' + e.message); } finally { setStarting(null); }
  };

  const handleTranslateExisting = async (sub: ExistingSubtitle) => {
    const label = LANG_NAMES[sub.language || 'und'] || sub.language;
    if (!await confirm(`Traduire "${sub.filename}" (${label}) ?`)) return;
    setStarting('existing');
    try { const task = await api.translateExistingSubtitle(film!.id, sub.path, sub.language || undefined); await api.startTranslation(task.id); refreshTasks(); toast.info('Traduction lancée'); }
    catch (e: any) { toast.error('Erreur : ' + e.message); } finally { setStarting(null); }
  };

  const handleImproveExisting = async (sub: ExistingSubtitle) => {
    setStarting('existing');
    try { const task = await api.translateExistingSubtitle(film!.id, sub.path, sub.language || undefined, 'improve'); await api.startTranslation(task.id); refreshTasks(); toast.info('Amélioration lancée'); }
    catch (e: any) { toast.error('Erreur : ' + e.message); } finally { setStarting(null); }
  };

  const handleAnalyze = async () => {
    setAnalyzing(true);
    try { await api.analyzeFilm(film!.id); refreshFilm(); toast.info('Analyse contextuelle lancée'); }
    catch (e: any) { toast.error('Erreur analyse : ' + e.message); } finally { setAnalyzing(false); }
  };

  const handleRescan = async () => {
    if (!await confirm('Rescanner ce film ? Les métadonnées seront mises à jour.')) return;
    setRescanning(true);
    try { await api.rescanFilm(film!.id); toast.info('Rescan lancé'); setTimeout(() => refreshFilm(), 3000); }
    catch (e: any) { toast.error('Erreur : ' + e.message); } finally { setRescanning(false); }
  };

  const handleEnrich = async () => {
    setEnriching(true);
    try { const result = await api.enrichFilm(film!.id); if (result.fields_updated) { refreshFilm(); toast.success(`Enrichi depuis ${result.source === 'tmdb' ? 'TMDB' : 'IMDb'} !`); } else { toast.info('Aucune nouvelle métadonnée.'); } }
    catch (e: any) { toast.error('Erreur enrichissement : ' + e.message); } finally { setEnriching(false); }
  };

  const handleTranscribe = async () => {
    if (!await confirm(`Lancer la transcription Whisper (${whisperModel}) ?\nCela peut prendre du temps sur CPU.`)) return;
    setTranscribing(true);
    try { await api.transcribeFilm(film!.id, whisperModel); toast.info('Transcription Whisper lancée'); }
    catch (e: any) { toast.error('Erreur : ' + e.message); } finally { setTranscribing(false); }
  };

  const handleSync = async (sub: ExistingSubtitle) => {
    if (!await confirm(`Synchroniser "${sub.filename}" ?`)) return;
    setStarting('existing');
    try { const task = await api.translateExistingSubtitle(film!.id, sub.path, sub.language || undefined, 'sync'); await api.startTranslation(task.id); refreshTasks(); toast.info('Synchronisation lancée'); }
    catch (e: any) { toast.error('Erreur : ' + e.message); } finally { setStarting(null); }
  };

  const handleLoadTracks = async () => {
    if (!film?.video_path) { toast.error('Aucun fichier vidéo.'); return; }
    setLoadingTracks(true);
    try { const r = await api.getFilmTracks(film.id); setTracks({ audio: r.audio || [], subtitle: r.subtitle || [], video: r.video || [] }); }
    catch (e: any) { toast.error('Erreur pistes : ' + e.message); } finally { setLoadingTracks(false); }
  };

  const handleExtractSubs = async () => {
    setExtractingTracks(true);
    try { const r = await api.extractSubtitles(film!.id); if (r.message) { toast.info(r.message); } else { toast.success(`${r.tracks?.length || 0} piste(s) extraite(s)`); } api.getFilmSubtitles(id!).then(setSubtitles).catch(() => {}); }
    catch (e: any) { toast.error('Extraction erreur : ' + e.message); } finally { setExtractingTracks(false); }
  };

  const handleCleanWork = async () => {
    if (!await confirm('Supprimer les fichiers de travail ?\nLe dossier source ne sera pas modifié.')) return;
    try { await api.cleanWorkFiles(film!.id); toast.success('Fichiers nettoyés'); } catch (e: any) { toast.error('Erreur : ' + e.message); }
  };

  const handleInstall = async (taskId: string) => {
    if (!await confirm('Installer le sous-titre dans le dossier source ?')) return;
    setInstalling(taskId);
    try { const r = await api.installSubtitle(taskId); toast.success(`Installé : ${r.destination}`); } catch (e: any) { toast.error('Erreur : ' + e.message); } finally { setInstalling(null); }
  };

  const handlePipeline = async () => {
    setPipelineDialog(true);
  };

  const handlePipelineLaunch = async () => {
    if (!film || !id) return;
    setPipelineDialog(false);
    setStarting('pipeline');
    try {
      const task = await api.pipelineFilm(id);
      await api.startTranslation(task.id, { pipeline_steps: pipelineSteps });
      refreshTasks();
      toast.info('Pipeline lancé');
      // Reload translations after pipeline completes (poll)
      setTimeout(() => api.listTranslations(id).then(r => setTranslations(r.versions)).catch(() => {}), 5000);
      setTimeout(() => api.listTranslations(id).then(r => setTranslations(r.versions)).catch(() => {}), 30000);
    } catch (e: any) { toast.error('Erreur : ' + e.message); }
    finally { setStarting(null); }
  };

  const handleInstallVersion = async (path: string) => {
    if (!id) return;
    if (!await confirm('Installer cette version dans le dossier du film ?')) return;
    setInstalling(path);
    try {
      const r = await api.installTranslation(id, path);
      toast.success(`Installé : ${r.destination}${r.backup ? ` (backup: ${r.backup})` : ''}`);
    } catch (e: any) { toast.error('Erreur : ' + e.message); }
    finally { setInstalling(null); }
  };

  // ── Preview handlers ──
  const openTaskPreview = useCallback((taskId: string) => {
    setPreviewTaskId(taskId);
    setPreviewVersionPath(null);
    setPreviewVersionContent(null);
  }, []);

  const openVersionPreview = useCallback(async (path: string) => {
    if (!id) return;
    setPreviewVersionPath(path);
    setPreviewTaskId(null);
    setPreviewVersionLoading(true);
    setPreviewVersionContent(null);
    try {
      const result = await api.readTranslationContent(id, path);
      setPreviewVersionContent(result.lines);
    } catch (e: any) {
      toast.error('Erreur lecture : ' + e.message);
      setPreviewVersionPath(null);
    } finally {
      setPreviewVersionLoading(false);
    }
  }, [id]);

  const closePreview = useCallback(() => {
    setPreviewTaskId(null);
    setPreviewVersionPath(null);
    setPreviewVersionContent(null);
  }, []);

  const handleDelete = async () => {
    if (!await confirm('Supprimer ce film ?')) return;
    await api.deleteFilm(film!.id); navigate('/');
  };

  // ─── Render ──────────────────────────────────────────────────────────

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 animate-spin text-brand-400" /></div>;
  if (error || !film) return <div className="text-red-400 text-center py-12">Film introuvable</div>;
  const isAnalyzing = film.analysis_status === 'analyzing';
  const isFRExisting = (sub: ExistingSubtitle) => (sub.language || '').toLowerCase().startsWith('fr');

  return (
    <>
      <ToastBar />
      <ConfirmDlg />
      <PipelineDialog
        open={pipelineDialog}
        onClose={() => setPipelineDialog(false)}
        onLaunch={handlePipelineLaunch}
        steps={pipelineSteps}
        setStep={(k, v) => setPipelineSteps(s => ({ ...s, [k]: v }))}
      />

      {/* ── Preview modal (task-based) ── */}
      {previewTaskId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
          onClick={closePreview}
        >
          <div
            className="glass-card w-full max-w-4xl max-h-[85vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
              <h3 className="text-lg font-semibold text-gray-100">Aperçu du sous-titre</h3>
              <button onClick={closePreview} className="btn-ghost p-1.5">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="overflow-y-auto flex-1 p-6 pt-4">
              {taskContentLoading && (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="w-8 h-8 text-brand-400 animate-spin" />
                </div>
              )}
              {!taskContentLoading && taskContentLines && (
                <SubtitleViewer lines={taskContentLines} loading={false} />
              )}
              {!taskContentLoading && !taskContentLines && (
                <div className="py-16 text-center text-gray-500">Aucun contenu disponible.</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Preview modal (version-based) ── */}
      {previewVersionPath && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
          onClick={closePreview}
        >
          <div
            className="glass-card w-full max-w-4xl max-h-[85vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
              <h3 className="text-lg font-semibold text-gray-100">Aperçu du sous-titre</h3>
              <button onClick={closePreview} className="btn-ghost p-1.5">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="overflow-y-auto flex-1 p-6 pt-4">
              {previewVersionLoading && (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="w-8 h-8 text-brand-400 animate-spin" />
                </div>
              )}
              {!previewVersionLoading && previewVersionContent && (
                <SubtitleViewer lines={previewVersionContent} loading={false} />
              )}
              {!previewVersionLoading && !previewVersionContent && (
                <div className="py-16 text-center text-gray-500">Aucun contenu disponible.</div>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="page-container">

        {/* ─── Header ─────────────────────────────────────────────────── */}
        <div className="flex items-center gap-3 mb-8">
          <Link to="/" className="btn-ghost !p-2"><ArrowLeft className="w-4 h-4" /></Link>
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl font-bold truncate">{film.title}</h1>
            <div className="flex items-center gap-2 text-sm text-gray-500 mt-0.5 flex-wrap">
              {film.year && <span>{film.year}</span>}
              {film.director && <><span>·</span><span>de {film.director}</span></>}
              {film.genre && <><span>·</span><span>{film.genre}</span></>}
              {film.rating && <><span>·</span><span>⭐ {film.rating}</span></>}
            </div>
          </div>
          <button onClick={handleAnalyze} disabled={analyzing || isAnalyzing} className="btn-secondary !text-xs" title="Analyse contextuelle">
            {analyzing || isAnalyzing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Brain className="w-3.5 h-3.5" />}
            <span className="hidden sm:inline ml-1">{analyzing || isAnalyzing ? 'Analyse…' : 'Analyser'}</span>
          </button>
          <button onClick={handleEnrich} disabled={enriching} className="btn-ghost !p-2 text-gray-500 hover:text-brand-400" title="Enrichir depuis IMDb">
            {enriching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Film className="w-4 h-4" />}
          </button>
          <button onClick={handleRescan} disabled={rescanning} className="btn-ghost !p-2 text-gray-500 hover:text-brand-400" title="Rescanner">
            <RefreshCw className={`w-4 h-4 ${rescanning ? 'animate-spin' : ''}`} />
          </button>
          <button onClick={handleDelete} className="btn-ghost !p-2 text-gray-500 hover:text-red-400" title="Supprimer"><Trash2 className="w-4 h-4" /></button>
        </div>

        {/* ─── Active tasks ────────────────────────────────────────────── */}
        {filmTasks.length > 0 && (
          <div className="mb-6 space-y-2">
            {filmTasks.map(task => (
              <div key={task.id} className="flex items-center gap-3 bg-gray-800/60 rounded-lg px-4 py-2.5">
                <StatusBadge status={task.status} />
                <span className="text-sm text-gray-300 flex-1 truncate">
                  {task.source_filename}
                  {task.task_type && task.task_type !== 'translation' && (
                    <span className="ml-2 text-xs text-brand-400">({TASK_TYPE_LABELS[task.task_type] || task.task_type})</span>
                  )}
                </span>
                <TaskProgressBar status={task.status} progress={task.progress_pct} />
                {task.status === 'completed' && task.target_path && (
                  <>
                    <button onClick={() => openTaskPreview(task.id)} className="btn-ghost !text-xs !p-1.5" title="Aperçu">
                      <Eye className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={() => handleInstall(task.id)} disabled={installing === task.id} className="btn-secondary !text-xs">
                      <HardDriveDownload className="w-3 h-3" /> Installer
                    </button>
                  </>
                )}
              </div>
            ))}
          </div>
        )}

        {/* ─── Two-column layout ────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

          {/* ─── Left: Info sidebar ────────────────────────────────────── */}
          <div className="lg:col-span-1 space-y-4">
            <div className="glass-card p-4 space-y-0.5">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Informations</h3>
              <MetaRow label="Source" value={LANG_NAMES[film.source_language] || film.source_language.toUpperCase()} />
              <MetaRow label="Cible" value={LANG_NAMES[film.target_language] || film.target_language.toUpperCase()} />
              {film.director && <MetaRow label="Réalisateur" value={film.director} />}
              {film.year && <MetaRow label="Année" value={String(film.year)} />}
              {film.genre && <MetaRow label="Genre" value={film.genre} />}
              {film.studio && <MetaRow label="Studio" value={film.studio} />}
              {film.rating && <MetaRow label="Note" value={`⭐ ${film.rating}/10`} />}
              {film.imdb_id && (
                <>
                  <MetaRow label="IMDb" value={film.imdb_id} mono />
                  <a href={`https://www.imdb.com/title/${film.imdb_id}`} target="_blank" rel="noopener noreferrer" className="text-xs text-brand-400 hover:underline block py-0.5">Voir sur IMDb ↗</a>
                </>
              )}
              {film.tmdb_id && <MetaRow label="TMDB" value={film.tmdb_id} mono />}
              <MetaRow label="Sous-titres" value={film.has_existing_subs ? '✅ Oui' : '❌ Non'} />
              <MetaRow label="Analyse" value={
                isAnalyzing ? '🔄 En cours…' :
                film.analysis_status === 'failed' ? '❌ Échouée' :
                film.lore_summary ? '✅ Terminée' : '—'
              } />
              {film.path && <MetaRow label="Dossier" value={film.path.split('/').slice(-2).join('/')} mono />}
              {film.video_path && <MetaRow label="Vidéo" value={film.video_path.split('/').pop() || ''} mono />}
            </div>

            {/* Characters */}
            {film.characters.length > 0 && (
              <div className="glass-card p-4">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Personnages ({film.characters.length})</h3>
                <div className="space-y-1.5">
                  {film.characters.map((c: Character) => (
                    <div key={c.id || c.name} className="flex items-center gap-2 text-sm">
                      <span className={`w-2 h-2 rounded-full ${GENDER_COLORS[c.gender || 'unknown']?.split(' ')[0]}`} />
                      <span className="text-gray-200 font-medium">{c.name}</span>
                      {c.description && <span className="text-gray-500 text-xs ml-auto truncate max-w-[60%]">{c.description}</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Glossary */}
            {glossary.length > 0 && (
              <div className="glass-card p-4">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Glossaire ({glossary.length})</h3>
                <div className="space-y-1.5">
                  {glossary.map(g => (
                    <div key={g.id || g.source_term} className="flex items-center gap-2 text-sm">
                      <span className="text-white">{g.source_term}</span>
                      <span className="text-gray-600">→</span>
                      <span className="text-emerald-400">{g.target_term}</span>
                      {g.notes && <span className="text-gray-500 text-xs ml-auto truncate max-w-[40%]">{g.notes}</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* ─── Right: Main content ──────────────────────────────────── */}
          <div className="lg:col-span-2 space-y-5">

            {/* Summary & Lore */}
            {(film.summary || lore?.lore_summary) && (
              <div className="glass-card p-5">
                {film.summary && (
                  <div className={lore?.lore_summary ? 'mb-4 pb-4 border-b border-gray-700/40' : ''}>
                    <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Résumé</h3>
                    <p className="text-sm text-gray-300 whitespace-pre-line">{film.summary}</p>
                  </div>
                )}
                {lore?.lore_summary && (
                  <div>
                    <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Contexte narratif</h3>
                    <p className="text-sm text-gray-300 whitespace-pre-line">{lore.lore_summary}</p>
                  </div>
                )}
              </div>
            )}

            {/* ─── Subtitles ──────────────────────────────────────────── */}
            <Section title="Sous-titres" icon={<FileText className="w-4 h-4" />} isOpen={open.subs} onToggle={() => toggle('subs')}>
              <SubtitleUploader onUpload={handleUpload} disabled={uploading} />
              {subtitles.length > 0 && (
                <div className="mt-3 space-y-2">
                  {subtitles.map(sub => {
                    const label = LANG_NAMES[sub.language || 'und'] || sub.language;
                    return (
                      <div key={sub.path} className="flex items-center gap-3 bg-gray-800/40 rounded-lg px-3 py-2 group">
                        <FileText className="w-4 h-4 text-gray-400 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-gray-200 truncate">{sub.filename}</p>
                          <div className="flex items-center gap-2 text-xs text-gray-500">
                            <span>{label}</span><span>·</span><span>{sub.format}</span>
                            {sub.is_sdh && <span className="bg-yellow-500/20 text-yellow-300 px-1 rounded">SDH</span>}
                            {sub.source !== 'scanner' && <span className="text-brand-400">{sub.source}</span>}
                          </div>
                        </div>
                        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button onClick={() => handleTranslateExisting(sub)} disabled={starting !== null} className="btn-ghost !text-xs !p-1.5" title="Traduire"><Languages className="w-3.5 h-3.5" /></button>
                          <button onClick={() => handleImproveExisting(sub)} disabled={starting !== null} className="btn-ghost !text-xs !p-1.5 text-violet-400" title="Améliorer"><Sparkles className="w-3.5 h-3.5" /></button>
                          <button onClick={() => handleSync(sub)} disabled={starting !== null} className="btn-ghost !text-xs !p-1.5" title="Resynchroniser"><Clock className="w-3.5 h-3.5" /></button>
                          {isFRExisting(sub) && (
                            <button onClick={() => handleTranslateExisting(sub)} disabled={starting !== null} className="btn-ghost !text-xs !p-1.5 text-amber-400" title="Refaire"><ArrowRightLeft className="w-3.5 h-3.5" /></button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </Section>

            {/* ─── Pipeline (all-in-one) ──────────────────────────── */}
            <Section title="Pipeline" icon={<Play className="w-4 h-4" />} isOpen={open.pipeline} onToggle={() => toggle('pipeline')}>
              <p className="text-xs text-gray-400 mb-3">Extraction → Transcription → Analyse → Traduction → Installation automatique</p>
              <button
                onClick={handlePipeline}
                disabled={starting !== null || !film.video_path}
                className="btn-primary !text-sm w-full"
                title={!film.video_path ? 'Aucune vidéo détectée — lancez un scan d\'abord' : ''}
              >
                <Play className="w-4 h-4" />
                {starting !== null ? 'Lancement…' : 'Pipeline complet'}
              </button>
            </Section>

            {/* ─── Traductions (versionnées) ──────────────────────── */}
            <Section title="Traductions" icon={<Download className="w-4 h-4" />} isOpen={open.translations} onToggle={() => toggle('translations')}>
              {translations.length === 0 ? (
                <p className="text-xs text-gray-500 italic">Aucune traduction disponible. Lancez une traduction d'abord.</p>
              ) : (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {translations.map(v => (
                    <div key={v.path} className="flex items-center gap-3 bg-gray-800/40 rounded-lg px-3 py-2 group">
                      <Download className="w-4 h-4 text-brand-400 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-200 truncate">{v.filename}</p>
                        <p className="text-xs text-gray-500">
                          {v.created} · {(v.size / 1024).toFixed(1)} KB
                          {v.filename.includes('.pipeline.') && <span className="ml-1 text-brand-400">(pipeline)</span>}
                          {v.filename.includes('.improved.') && <span className="ml-1 text-violet-400">(amélioré)</span>}
                        </p>
                      </div>
                      <button
                        onClick={() => openVersionPreview(v.path)}
                        className="btn-ghost !text-xs !p-1.5 opacity-0 group-hover:opacity-100 transition-opacity"
                        title={`Aperçu de ${v.filename}`}
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleInstallVersion(v.path)}
                        disabled={installing !== null}
                        className="btn-ghost !text-xs !p-1.5 text-emerald-400 opacity-0 group-hover:opacity-100 transition-opacity"
                        title={`Installer ${v.filename} dans le dossier du film`}
                      >
                        <HardDriveDownload className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </Section>

            {/* ─── Embedded tracks ────────────────────────────────────── */}
            <Section title="Pistes embarquées" icon={<Disc className="w-4 h-4" />} isOpen={open.tracks} onToggle={() => toggle('tracks')}>
              <div className="flex gap-3 mb-3">
                <button onClick={handleLoadTracks} disabled={loadingTracks} className="btn-secondary !text-xs">
                  {loadingTracks ? <Loader2 className="w-3 h-3 animate-spin" /> : <Disc className="w-3 h-3" />} Analyser
                </button>
              </div>
              {tracks && (
                <div className="space-y-3">
                  {tracks.subtitle.length > 0 && (
                    <div>
                      <h4 className="text-xs text-gray-500 mb-1">Sous-titres intégrés</h4>
                      {tracks.subtitle.map((t: TrackInfo, i: number) => (
                        <div key={i} className="text-sm text-gray-300 flex items-center gap-2 py-0.5">
                          <span className="text-xs bg-gray-700 px-1.5 py-0.5 rounded">{t.codec}</span>
                          <span>{t.language || 'und'}</span>
                          {t.title && <span className="text-gray-500 text-xs">({t.title})</span>}
                        </div>
                      ))}
                      <button onClick={handleExtractSubs} disabled={extractingTracks} className="btn-secondary !text-xs mt-2">
                        {extractingTracks ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />} Extraire les sous-titres
                      </button>
                    </div>
                  )}
                  {tracks.audio.length > 0 && (
                    <div>
                      <h4 className="text-xs text-gray-500 mb-1">Pistes audio</h4>
                      {tracks.audio.map((t: TrackInfo, i: number) => (
                        <div key={i} className="text-sm text-gray-300 flex items-center gap-2 py-0.5">
                          <span className="text-xs bg-gray-700 px-1.5 py-0.5 rounded">{t.codec}</span>
                          <span>{t.language || 'und'}</span>
                          {t.channels && <span className="text-xs text-gray-500">{t.channels}ch</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </Section>

            {/* ─── Whisper ─────────────────────────────────────────────── */}
            <Section title="Transcription Whisper" icon={<Mic className="w-4 h-4" />} isOpen={open.whisper} onToggle={() => toggle('whisper')}>
              <div className="flex items-center gap-3">
                <select value={whisperModel} onChange={e => setWhisperModel(e.target.value)} className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm">
                  <option value="tiny">Tiny (rapide)</option>
                  <option value="base">Base</option>
                  <option value="small">Small</option>
                  <option value="medium">Medium</option>
                  <option value="large">Large (lent)</option>
                </select>
                <button onClick={handleTranscribe} disabled={transcribing} className="btn-primary !text-xs">
                  {transcribing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Mic className="w-3 h-3" />} Lancer
                </button>
              </div>
              <p className="text-xs text-gray-500 mt-2">Génère des sous-titres à partir de l'audio. Nécessite faster-whisper.</p>
            </Section>

            {/* ─── Video player ────────────────────────────────────────── */}
            {film.video_path && (
              <Section title="Lecteur vidéo" icon={<Film className="w-4 h-4" />} isOpen={open.video} onToggle={() => toggle('video')}>
                <video controls className="w-full rounded-lg bg-black" style={{ maxHeight: '40vh' }}>
                  <source src={api.getFilmVideoUrl(film.id)} type="video/mp4" />
                  Votre navigateur ne supporte pas la lecture vidéo.
                </video>
                <p className="text-xs text-gray-500 mt-1">Lecteur local — ne fonctionne pas pour les sources SSH.</p>
              </Section>
            )}

            {/* ─── Work files ──────────────────────────────────────────── */}
            <div className="flex items-center gap-3">
              <button onClick={handleCleanWork} className="btn-ghost !text-xs text-red-400 hover:text-red-300">
                <Trash2 className="w-3 h-3" /> Nettoyer les fichiers de travail
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// ─── Toast / Confirm components ──────────────────────────────────────────

function ToastBar() {
  const toasts = useToasts();
  if (!toasts.length) return null;
  return (
    <div className="fixed top-4 right-4 z-[100] space-y-2 max-w-sm">
      {toasts.map(t => (
        <div key={t.id} className={`flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium animate-slide-in-right ${
          t.type === 'error' ? 'bg-red-500/90 text-white' : t.type === 'success' ? 'bg-emerald-500/90 text-white' : 'bg-brand-500/90 text-white'
        }`}>
          {t.type === 'error' && <AlertCircle className="w-4 h-4 shrink-0" />}
          {t.type === 'success' && <Check className="w-4 h-4 shrink-0" />}
          <span className="flex-1">{t.message}</span>
          <button onClick={() => { toastState = toastState.filter(x => x.id !== t.id); toastListeners.forEach(l => l([...toastState])); }} className="opacity-70 hover:opacity-100"><X className="w-3.5 h-3.5" /></button>
        </div>
      ))}
    </div>
  );
}

function PipelineDialog({ open, onClose, onLaunch, steps, setStep }: {
  open: boolean; onClose: () => void; onLaunch: () => void;
  steps: Record<string, boolean>;
  setStep: (key: string, v: boolean) => void;
}) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [open, onClose]);

  if (!open) return null;

  const STEP_LABELS: Record<string, string> = {
    extract: 'Extraire les sous-titres intégrés',
    transcribe: 'Transcrire avec Whisper (si pas de sous-titre)',
    analyze: 'Analyser le contexte (personnages, glossaire, résumé)',
    translate: 'Traduire (draft + refine)',
    install: 'Installer dans le dossier source (.fre.srt)',
  };

  const stepsOrder = ['extract', 'transcribe', 'analyze', 'translate', 'install'];

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70">
      <div className="bg-gray-800 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl border border-white/10">
        <h3 className="text-white text-lg font-bold mb-1">Configuration du pipeline</h3>
        <p className="text-gray-400 text-xs mb-5">Choisissez les étapes à exécuter :</p>
        <div className="space-y-3 mb-6">
          {stepsOrder.map(key => (
            <label key={key} className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={steps[key]}
                onChange={e => setStep(key, e.target.checked)}
                className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-brand-500 focus:ring-brand-500"
              />
              <span className="text-sm text-gray-300">{STEP_LABELS[key]}</span>
            </label>
          ))}
        </div>
        <div className="flex gap-3 justify-end">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition">Annuler</button>
          <button onClick={onLaunch} className="px-4 py-2 text-sm rounded-lg bg-brand-500 text-white hover:bg-brand-600 transition">Lancer</button>
        </div>
      </div>
    </div>
  );
}

function ConfirmDlg() {
  const { open, message, yes, no } = useConfirm();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[99] flex items-center justify-center bg-black/60">
      <div className="bg-gray-800 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl border border-white/10">
        <p className="text-white text-sm mb-6 whitespace-pre-line">{message}</p>
        <div className="flex gap-3 justify-end">
          <button onClick={no} className="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition">Annuler</button>
          <button onClick={yes} className="px-4 py-2 text-sm rounded-lg bg-brand-500 text-white hover:bg-brand-600 transition">Confirmer</button>
        </div>
      </div>
    </div>
  );
}

// ─── Layout helpers ──────────────────────────────────────────────────────

function Section({ title, icon, isOpen, onToggle, children }: { title: string; icon: React.ReactNode; isOpen: boolean; onToggle: () => void; children: React.ReactNode }) {
  return (
    <div className="glass-card p-5">
      <button onClick={onToggle} className="flex items-center gap-2 w-full text-left group">
        <span className="text-brand-400">{icon}</span>
        <h3 className="text-sm font-semibold text-gray-200 flex-1">{title}</h3>
        <ChevronDown className={`w-4 h-4 text-gray-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>
      {isOpen && <div className="mt-4">{children}</div>}
    </div>
  );
}

function MetaRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between items-center py-1 border-b border-gray-800/30 last:border-0">
      <span className="text-xs text-gray-500">{label}</span>
      <span className={`${mono ? 'font-mono text-xs text-gray-400' : 'text-sm text-gray-200'} truncate ml-4 text-right`}>{value}</span>
    </div>
  );
}