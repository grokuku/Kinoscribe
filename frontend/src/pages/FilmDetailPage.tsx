import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Trash2, Users, Languages, Play, Download,
  Film, Brain, BookOpen, FileText, ChevronRight, Mic, RefreshCw,
  Subtitles, Upload, Zap, MessageSquare, Disc, HardDriveDownload,
  Video, Clock, Sparkles, ArrowRightLeft, AlertCircle, Loader2,
} from 'lucide-react';
import { useFilm, useTasks, useActiveTaskPolling } from '../hooks/useApi';
import { api } from '../api/client';
import { StatusBadge, TaskProgressBar } from '../components/TaskStatus';
import SubtitleUploader from '../components/SubtitleUploader';
import type { Task, TaskType, Character, GlossaryEntry, ExistingSubtitle, TrackInfo } from '../types';

type Tab = 'profile' | 'translation';

const LANG_NAMES: Record<string, string> = {
  en: 'Anglais', fr: 'Français', es: 'Espagnol', de: 'Allemand',
  it: 'Italien', pt: 'Portugais', ja: 'Japonais', ko: 'Coréen', zh: 'Chinois',
  und: 'Inconnu',
};

const GENDER_COLORS: Record<string, string> = {
  male: 'bg-blue-500/15 text-blue-300',
  female: 'bg-pink-500/15 text-pink-300',
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

  // Load enrichments when film is loaded
  useEffect(() => {
    if (id) {
      api.getFilmGlossary(id).then(setGlossary).catch(() => {});
      api.getFilmLore(id).then(setLore).catch(() => {});
      api.getFilmSubtitles(id).then(setSubtitles).catch(() => {});
    }
  }, [id, filmTasks?.length]);

  // Auto-refresh when analysis is running
  useEffect(() => {
    if (film?.analysis_status === 'analyzing') {
      const timer = setInterval(() => refreshFilm(), 3000);
      return () => clearInterval(timer);
    }
  }, [film?.analysis_status, refreshFilm]);

  // Auto-refresh lore when analysis completes
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
    } catch (e: any) { alert('Upload erreur : ' + e.message); }
    finally { setUploading(false); }
  };

  const handleStart = async (taskId: string) => {
    setStarting(taskId);
    try { await api.startTranslation(taskId); refreshTasks(); }
    catch (e: any) { alert('Démarrage erreur : ' + e.message); }
    finally { setStarting(null); }
  };

  const handleCreateTask = async (sub: ExistingSubtitle, taskType: TaskType = 'translation') => {
    const label = TASK_TYPE_LABELS[taskType] || taskType;
    if (!confirm(`${label} : "${sub.filename}" (${LANG_NAMES[sub.language || 'und'] || sub.language}) ?`)) return;
    setStarting('existing');
    try {
      const task = await api.translateExistingSubtitle(film!.id, sub.path, sub.language || undefined, taskType);
      await api.startTranslation(task.id);
      refreshTasks(); refreshFilm();
    } catch (e: any) { alert('Erreur : ' + e.message); }
    finally { setStarting(null); }
  };

  const handleAnalyze = async () => {
    setAnalyzing(true);
    try {
      await api.analyzeFilm(film!.id);
      refreshFilm(); // Will now show analysis_status = 'analyzing'
    } catch (e: any) { alert('Erreur : ' + e.message); }
    finally { setAnalyzing(false); }
  };

  const handleRescan = async () => {
    if (!confirm('Rescanner ce film ? Les métadonnées seront mises à jour à partir du dossier source.')) return;
    setRescanning(true);
    try {
      await api.rescanFilm(film!.id);
      alert('Rescan lancé en arrière-plan');
      setTimeout(() => refreshFilm(), 3000);
    } catch (e: any) { alert('Erreur : ' + e.message); }
    finally { setRescanning(false); }
  };

  const handleEnrich = async () => {
    setEnriching(true);
    try {
      const result = await api.enrichFilm(film!.id);
      if (result.fields_updated) {
        refreshFilm();
        alert(`Metadonnées enrichies depuis ${result.source === 'tmdb' ? 'TMDB' : 'IMDb'} !`);
      } else {
        alert('Aucune nouvelle métadonnée trouvée.');
      }
    } catch (e: any) { alert('Erreur enrichissement : ' + e.message); }
    finally { setEnriching(false); }
  };

  const handleTranscribe = async () => {
    if (!confirm(`Lancer la transcription Whisper (${whisperModel}) ?\nCela peut prendre du temps sur CPU.`)) return;
    setTranscribing(true);
    try {
      await api.transcribeFilm(film!.id, whisperModel);
      alert('Transcription Whisper lancée en arrière-plan');
      setTimeout(() => api.getFilmSubtitles(id!).then(setSubtitles), 10000);
    } catch (e: any) { alert('Erreur : ' + e.message); }
    finally { setTranscribing(false); }
  };

  const handleSync = async (sub: ExistingSubtitle) => {
    if (!confirm(`Créer une tâche de synchronisation pour "${sub.filename}" ?`)) return;
    setStarting('existing');
    try {
      const task = await api.translateExistingSubtitle(film!.id, sub.path, sub.language || undefined, 'sync');
      await api.startTranslation(task.id);
      refreshTasks();
    } catch (e: any) { alert('Erreur : ' + e.message); }
    finally { setStarting(null); }
  };

  const onProbeTracks = async () => {
    if (!film?.video_path) { alert('Aucun fichier vidéo trouvé.'); return; }
    setLoadingTracks(true);
    try {
      const result = await api.getFilmTracks(film.id);
      setTracks({ audio: result.audio || [], subtitle: result.subtitle || [], video: result.video || [] });
    } catch (e: any) { alert('Erreur pistes : ' + e.message); }
    finally { setLoadingTracks(false); }
  };

  const onExtractSubtitles = async () => {
    setExtractingTracks(true);
    try {
      const result = await api.extractSubtitles(film!.id);
      if (result.message) { alert(result.message); }
      else { alert(`${result.tracks?.length || 0} piste(s) extraite(s)`); }
      api.getFilmSubtitles(id!).then(setSubtitles).catch(() => {});
      setTracks(null);
    } catch (e: any) { alert('Extraction erreur : ' + e.message); }
    finally { setExtractingTracks(false); }
  };

  const onCleanWorkFiles = async () => {
    if (!confirm('Supprimer tous les fichiers de travail ?\nLe dossier source du film ne sera pas modifié.')) return;
    try {
      await api.cleanWorkFiles(film!.id, 'all');
      api.getFilmSubtitles(id!).then(setSubtitles).catch(() => {});
      setTracks(null);
    } catch (e: any) { alert('Nettoyage erreur : ' + e.message); }
  };

  const onInstallSubtitle = async (taskId: string) => {
    if (!confirm('Installer le sous-titre traduit dans le dossier source du film ?')) return;
    setInstalling(taskId);
    try {
      const result = await api.installSubtitle(taskId);
      alert(`Sous-titre installé : ${result.destination}`);
      api.getFilmSubtitles(id!).then(setSubtitles).catch(() => {});
      refreshFilm();
    } catch (e: any) { alert('Installation erreur : ' + e.message); }
    finally { setInstalling(null); }
  };

  if (loading) return <div className="flex items-center justify-center py-32"><div className="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" /></div>;
  if (error || !film) return <div className="text-red-400 text-center py-20">Film non trouvé</div>;

  const pendingTasks = filmTasks.filter((t) => t.status === 'pending' || t.status === 'failed');
  const completedTasks = filmTasks.filter((t) => t.status === 'completed');
  const activeTasks = filmTasks.filter((t) => !['completed', 'failed'].includes(t.status));
  const isAnalyzing = film.analysis_status === 'analyzing';

  return (
    <div className="animate-fade-in space-y-6">
      {/* Back + header */}
      <div className="flex items-center gap-4">
        <Link to="/" className="btn-ghost !p-2"><ArrowLeft className="w-5 h-5" /></Link>
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold text-gray-100 truncate">{film.title}</h1>
          <div className="flex items-center gap-2 text-sm text-gray-500 mt-0.5">
            {film.year && <span>{film.year}</span>}
            {film.director && <span>· de {film.director}</span>}
            <span className="flex items-center gap-1"><Languages className="w-3 h-3" />{film.source_language.toUpperCase()} → {film.target_language.toUpperCase()}</span>
            {isAnalyzing && <span className="flex items-center gap-1 text-brand-400"><Loader2 className="w-3 h-3 animate-spin" />Analyse en cours...</span>}
          </div>
        </div>
        <button onClick={handleRescan} disabled={rescanning} className="btn-ghost !p-2 text-gray-600 hover:text-brand-400" title="Rescanner le film">
          {rescanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
        </button>
        <button onClick={async () => { if (!confirm('Supprimer ce film ?')) return; await api.deleteFilm(film.id); navigate('/'); }} className="btn-ghost !p-2 text-gray-600 hover:text-red-400"><Trash2 className="w-4 h-4" /></button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-white/[0.06]">
        {(['profile', 'translation'] as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-all ${tab === t ? 'text-brand-300 border-brand-500' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
            {t === 'profile' ? '📊 Fiche film' : '🔄 Traduction'}
          </button>
        ))}
      </div>

      {tab === 'profile' && (
        <ProfileTab film={film} glossary={glossary} lore={lore} characters={film.characters} onAnalyze={handleAnalyze} analyzing={analyzing || isAnalyzing} onEnrich={handleEnrich} enriching={enriching} />
      )}
      {tab === 'translation' && (
        <TranslationTab
          filmId={film.id} film={film} filmTasks={filmTasks}
          subtitles={subtitles} pendingTasks={pendingTasks} completedTasks={completedTasks}
          activeTasks={activeTasks} onStart={handleStart} starting={starting} onUpload={handleUpload} uploading={uploading}
          onCreateTask={handleCreateTask} onTranscribe={handleTranscribe} transcribing={transcribing}
          onSync={handleSync} whisperModel={whisperModel} setWhisperModel={setWhisperModel}
          onAnalyze={handleAnalyze} analyzing={analyzing || isAnalyzing}
          tracks={tracks} loadingTracks={loadingTracks} extractingTracks={extractingTracks}
          onProbeTracks={onProbeTracks} onExtractSubtitles={onExtractSubtitles} onClearTracks={() => setTracks(null)} onCleanWorkFiles={onCleanWorkFiles} onInstall={onInstallSubtitle} installing={installing}
        />
      )}
    </div>
  );
}

// ─── Profile Tab ────────────────────────────────────────────────────────────

function ProfileTab({ film, glossary, lore, characters, onAnalyze, analyzing, onEnrich, enriching }: {
  film: any; glossary: GlossaryEntry[]; lore: any; characters: Character[];
  onAnalyze: () => void; analyzing: boolean; onEnrich: () => void; enriching: boolean;
}) {
  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 animate-fade-in">
      <div className="xl:col-span-2 space-y-6">
        {/* Lore summary */}
        <div>
          <h2 className="section-title flex items-center gap-2">Résumé narratif
            {analyzing ? (
              <Loader2 className="w-4 h-4 animate-spin text-brand-400" />
            ) : (
              <button onClick={onAnalyze} disabled={analyzing} className="btn-ghost !p-1 text-brand-400 hover:text-brand-300" title="Lancer l'analyse contextuelle"><Brain className="w-4 h-4" /></button>
            )}
          </h2>
          <div className="glass-card p-5">
            {analyzing ? (
              <p className="text-sm text-brand-400 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Analyse en cours...</p>
            ) : lore?.lore_summary ? (
              <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">{lore.lore_summary}</p>
            ) : (
              <p className="text-sm text-gray-600 italic">Aucun résumé — cliquez 🧠 pour lancer l'analyse contextuelle</p>
            )}
          </div>
        </div>

        {/* Characters */}
        <div>
          <h2 className="section-title flex items-center gap-2"><Users className="w-4 h-4" /> Personnages</h2>
          {characters.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {characters.map((c) => (
                <div key={c.name} className="glass-card p-3 flex items-start gap-3">
                  <span className={`badge flex-shrink-0 ${GENDER_COLORS[c.gender] || GENDER_COLORS.unknown}`}>
                    {c.gender === 'male' ? '♂' : c.gender === 'female' ? '♀' : '?'}
                  </span>
                  <div className="min-w-0"><p className="text-sm font-medium text-gray-200 truncate">{c.name}</p>{c.description && <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{c.description}</p>}</div>
                </div>
              ))}
            </div>
          ) : <p className="text-sm text-gray-600 italic">Aucun personnage identifié</p>}
        </div>

        {/* Glossary */}
        <div>
          <h2 className="section-title flex items-center gap-2"><BookOpen className="w-4 h-4" /> Glossaire</h2>
          {glossary.length > 0 ? (
            <div className="glass-card overflow-hidden">
              <table className="w-full text-sm"><thead><tr className="border-b border-white/[0.06]"><th className="px-4 py-2 text-left text-gray-500 font-medium">Source</th><th className="px-4 py-2 text-left text-gray-500 font-medium">Cible</th><th className="px-4 py-2 text-left text-gray-500 font-medium">Notes</th></tr></thead>
              <tbody>{glossary.map((g, i) => <tr key={i} className="border-b border-white/[0.03]"><td className="px-4 py-2 text-gray-300 font-mono">{g.source_term}</td><td className="px-4 py-2 text-brand-300 font-mono">{g.target_term}</td><td className="px-4 py-2 text-gray-500">{g.notes || '—'}</td></tr>)}</tbody>
              </table>
            </div>
          ) : <p className="text-sm text-gray-600 italic">Aucun glossaire</p>}
        </div>
      </div>

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
          film.analysis_status === 'analyzing' ? '🔄 En cours' :
          film.analysis_status === 'failed' ? '❌ Échouée' : '✅ OK'
        } />
      </div>
    </div>
  );
}

// ─── Translation Tab ─────────────────────────────────────────────────────────

function TranslationTab({
  filmId, film, filmTasks, subtitles, pendingTasks, completedTasks,
  activeTasks, onStart, starting, onUpload, uploading, onCreateTask,
  onTranscribe, transcribing, onSync,
  whisperModel, setWhisperModel,
  onAnalyze, analyzing,
  tracks, loadingTracks, extractingTracks,
  onProbeTracks, onExtractSubtitles, onClearTracks, onCleanWorkFiles, onInstall, installing,
}: {
  filmId: string; film: any; filmTasks: Task[]; subtitles: ExistingSubtitle[];
  pendingTasks: Task[]; completedTasks: Task[];
  activeTasks: Task[];
  onStart: (id: string) => void; starting: string | null;
  onUpload: (file: File) => void; uploading: boolean;
  onCreateTask: (sub: ExistingSubtitle, type: TaskType) => void;
  onTranscribe: () => void; transcribing: boolean;
  onSync: (sub: ExistingSubtitle) => void;
  whisperModel: string; setWhisperModel: (m: string) => void;
  onAnalyze: () => void; analyzing: boolean;
  tracks: { audio: TrackInfo[]; subtitle: TrackInfo[]; video: TrackInfo[] } | null;
  loadingTracks: boolean; extractingTracks: boolean;
  onProbeTracks: () => void; onExtractSubtitles: () => void; onClearTracks: () => void;
  onCleanWorkFiles: () => void;
  onInstall: (taskId: string) => void;
  installing: string | null;
}) {
  const hasVideo = !!film.video_path;
  const targetLang = film.target_language || 'fr';

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 animate-fade-in">
      <div className="xl:col-span-2 space-y-6">

        {/* Video player */}
        {hasVideo && <VideoPlayer filmId={filmId} videoPath={film.video_path} />}

        {/* Active tasks indicator */}
        {activeTasks.length > 0 && (
          <div className="glass-card p-4 border border-brand-500/20">
            <div className="flex items-center gap-2 mb-3">
              <Loader2 className="w-4 h-4 animate-spin text-brand-400" />
              <h3 className="text-sm font-semibold text-brand-300">{activeTasks.length} tâche(s) en cours</h3>
            </div>
            <div className="space-y-2">
              {activeTasks.map((task) => (
                <div key={task.id} className="flex items-center gap-3 text-sm">
                  <span className="text-gray-400 font-mono truncate">{task.source_filename}</span>
                  <StatusBadge status={task.status} />
                  <span className="text-gray-500 text-xs">{TASK_TYPE_LABELS[task.task_type] || task.task_type}</span>
                  <TaskProgressBar status={task.status} progress={task.progress_pct} />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Existing subtitles */}
        {subtitles.length > 0 && (
          <div>
            <h2 className="section-title flex items-center gap-2"><Subtitles className="w-4 h-4" /> Sous-titres disponibles</h2>
            <div className="space-y-2">
              {subtitles.map((sub) => (
                <SubtitleCard
                  key={sub.path}
                  sub={sub}
                  targetLang={targetLang}
                  starting={starting}
                  onCreateTask={onCreateTask}
                  onSync={onSync}
                />
              ))}
            </div>
          </div>
        )}

        {/* Upload */}
        <div>
          <h2 className="section-title flex items-center gap-2"><Upload className="w-4 h-4" /> Ajouter un sous-titre</h2>
          <p className="text-xs text-gray-600 mb-3">Optionnel — uploadez un fichier si aucun sous-titre n'est disponible</p>
          <SubtitleUploader onUpload={onUpload} disabled={uploading} />
        </div>

        {/* All tasks */}
        <div>
          <h2 className="section-title">Tâches</h2>
          {filmTasks.length === 0 ? (
            <p className="text-sm text-gray-600 glass-card p-6 text-center">Aucune tâche — sélectionnez un sous-titre ci-dessus ou uploadez-en un.</p>
          ) : (
            <div className="space-y-3">
              {filmTasks.map((task) => (
                <div key={task.id} className="glass-card p-4 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-mono text-gray-300 truncate">{task.source_filename}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[10px] badge bg-gray-500/15 text-gray-400">{TASK_TYPE_LABELS[task.task_type] || task.task_type}</span>
                      <StatusBadge status={task.status} />
                      <TaskProgressBar status={task.status} progress={task.progress_pct} />
                    </div>
                    {task.error_message && <p className="text-xs text-red-400 mt-1 truncate">{task.error_message}</p>}
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {task.status === 'pending' && <button onClick={() => onStart(task.id)} disabled={!!starting} className="btn-primary !py-1.5 !px-3 !text-xs">{starting === task.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />} Lancer</button>}
                    {task.status === 'completed' && (
                      <>
                        <a href={`/api/tasks/${task.id}/download`} className="btn-primary !py-1.5 !px-3 !text-xs"><Download className="w-3 h-3" /> Télécharger</a>
                        <button onClick={() => onInstall(task.id)} disabled={!!installing} className="btn-secondary !py-1.5 !px-3 !text-xs">
                          {installing === task.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <HardDriveDownload className="w-3 h-3" />} Installer
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Sidebar: tools */}
      <div className="space-y-4">
        <h2 className="section-title">Outils</h2>

        {/* Manual analysis */}
        <div className="glass-card p-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2"><Brain className="w-4 h-4 text-brand-400" /> Analyse contextuelle</h3>
          <p className="text-xs text-gray-500">Analyse les personnages, résume l'intrigue, crée le glossaire.</p>
          {film.analysis_status === 'analyzing' ? (
            <div className="flex items-center gap-2 text-sm text-brand-400"><Loader2 className="w-4 h-4 animate-spin" /> Analyse en cours...</div>
          ) : (
            <button onClick={onAnalyze} disabled={analyzing} className="btn-secondary w-full !text-xs">{analyzing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />} Lancer l'analyse</button>
          )}
        </div>

        {/* Whisper transcription */}
        <div className="glass-card p-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2"><Mic className="w-4 h-4 text-violet-400" /> Whisper</h3>
          {!hasVideo ? (
            <p className="text-xs text-gray-600">Pas de fichier vidéo détecté.</p>
          ) : (
            <>
              <p className="text-xs text-gray-500">Reconnaissance vocale ou resynchronisation des timings.</p>
              <div>
                <label className="block text-[10px] font-semibold text-gray-500 uppercase mb-1">Modèle</label>
                <select value={whisperModel} onChange={(e) => setWhisperModel(e.target.value)} className="select-field !py-1.5 !text-xs !w-full">
                  {['tiny', 'base', 'small', 'medium', 'large'].map((m) => <option key={m} value={m}>{m}{m === 'medium' ? ' (recommandé)' : ''}</option>)}
                </select>
              </div>
              <button onClick={onTranscribe} disabled={transcribing} className="btn-secondary w-full !text-xs">
                {transcribing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Mic className="w-3 h-3" />} Transcrire l'audio
              </button>
            </>
          )}
        </div>

        {/* Embedded tracks */}
        {hasVideo && (
        <div className="glass-card p-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2"><Disc className="w-4 h-4 text-cyan-400" /> Pistes embarquées</h3>
          <p className="text-xs text-gray-500">Inspectez les pistes audio et sous-titres intégrées.</p>
          {!tracks ? (
            <button onClick={onProbeTracks} disabled={loadingTracks} className="btn-secondary w-full !text-xs">
              {loadingTracks ? <Loader2 className="w-3 h-3 animate-spin" /> : <Disc className="w-3 h-3" />} Analyser les pistes
            </button>
          ) : (
            <div className="space-y-3">
              {tracks.subtitle.length > 0 && (
                <div>
                  <p className="text-[10px] font-semibold text-gray-400 uppercase mb-1">Sous-titres intégrés</p>
                  <div className="space-y-1">
                    {tracks.subtitle.map((t: TrackInfo) => (
                      <div key={t.index} className="flex items-center justify-between text-xs">
                        <span className="text-gray-300 truncate">{(t.title && t.title !== t.language) ? t.title : (LANG_NAMES[t.language || 'und'] || t.language?.toUpperCase() || 'Inconnu')}</span>
                        <span className="flex items-center gap-1">
                          <span className="text-[10px] text-gray-600 font-mono">{t.codec}</span>
                          {t.default && <span className="text-[10px] badge bg-emerald-500/15 text-emerald-300">Défaut</span>}
                          {t.forced && <span className="text-[10px] badge bg-orange-500/15 text-orange-300">Forcé</span>}
                          {t.extractable === false && <span className="text-[10px] text-gray-600">🖼 Image</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {tracks.audio.length > 0 && (
                <div>
                  <p className="text-[10px] font-semibold text-gray-400 uppercase mb-1">Pistes audio</p>
                  <div className="space-y-1">
                    {tracks.audio.map((t: TrackInfo) => (
                      <div key={t.index} className="flex items-center justify-between text-xs">
                        <span className="text-gray-300 truncate">{t.title || (LANG_NAMES[t.language || 'und'] || t.language?.toUpperCase() || 'Inconnu')}</span>
                        <span className="text-[10px] text-gray-600">{t.channels}ch {t.codec}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {tracks.video.length > 0 && (
                <div>
                  <p className="text-[10px] font-semibold text-gray-400 uppercase mb-1">Vidéo</p>
                  <div className="space-y-1">
                    {tracks.video.map((t: TrackInfo) => (
                      <div key={t.index} className="text-xs text-gray-500">{t.codec} {t.width}×{t.height}</div>
                    ))}
                  </div>
                </div>
              )}
              {tracks.subtitle.filter((t: TrackInfo) => t.extractable !== false).length > 0 && (
                <button onClick={onExtractSubtitles} disabled={extractingTracks} className="btn-primary w-full !text-xs">
                  {extractingTracks ? <Loader2 className="w-3 h-3 animate-spin" /> : <Subtitles className="w-3 h-3" />}
                  Extraire les sous-titres
                </button>
              )}
              <button onClick={onCleanWorkFiles} className="btn-ghost w-full !text-xs text-orange-400 hover:text-orange-300">🗑️ Nettoyer fichiers de travail</button>
              <button onClick={onClearTracks} className="btn-ghost w-full !text-xs text-gray-500">Masquer</button>
            </div>
          )}
        </div>
        )}

        {/* Stats */}
        <div className="glass-card p-4 space-y-2">
          <h3 className="text-xs font-semibold text-gray-500 uppercase">Stats</h3>
          <div className="flex justify-between text-xs"><span className="text-gray-500">Sous-titres dispo</span><span className="text-gray-300 font-mono">{subtitles.length}</span></div>
          <div className="flex justify-between text-xs"><span className="text-gray-500">Tâches</span><span className="text-gray-300 font-mono">{filmTasks.length}</span></div>
          <div className="flex justify-between text-xs"><span className="text-gray-500">Terminées</span><span className="text-gray-300 font-mono">{completedTasks.length}</span></div>
          <div className="flex justify-between text-xs"><span className="text-gray-500">En cours</span><span className="text-gray-300 font-mono">{activeTasks.length}</span></div>
        </div>
      </div>
    </div>
  );
}

// ─── Video Player ─────────────────────────────────────────────────────────────

function VideoPlayer({ filmId, videoPath }: { filmId: string; videoPath: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [subtitleUrl, setSubtitleUrl] = useState<string | null>(null);

  return (
    <div className="glass-card overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-white/[0.06]">
        <Video className="w-4 h-4 text-brand-400" />
        <h3 className="text-sm font-semibold text-gray-200">Lecteur vidéo</h3>
        <span className="text-xs text-gray-600 font-mono ml-auto">{videoPath.split('/').pop()}</span>
      </div>
      <div className="bg-black/50">
        <video
          ref={videoRef}
          className="w-full max-h-[480px] mx-auto"
          controls
          preload="metadata"
          crossOrigin="anonymous"
        >
          <source src={api.getFilmVideoUrl(filmId)} type="video/mp4" />
          {subtitleUrl && <track kind="subtitles" src={subtitleUrl} srcLang="fr" label="Français" default />}
          Votre navigateur ne supporte pas la lecture vidéo.
        </video>
      </div>
    </div>
  );
}

// ─── Subtitle Card with action menu ───────────────────────────────────────────

function SubtitleCard({ sub, targetLang, starting, onCreateTask, onSync }: {
  sub: ExistingSubtitle; targetLang: string; starting: string | null;
  onCreateTask: (sub: ExistingSubtitle, type: TaskType) => void;
  onSync: (sub: ExistingSubtitle) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const isFRExisting = sub.language === targetLang || sub.language === 'fr';

  return (
    <div className="glass-card p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <FileText className="w-4 h-4 text-brand-400 flex-shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-200 truncate font-mono">{sub.filename}</p>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-gray-500">{LANG_NAMES[sub.language || 'und'] || sub.language?.toUpperCase()}</span>
              {sub.is_sdh && <span className="text-[10px] badge bg-yellow-500/15 text-yellow-300">SDH</span>}
              {sub.is_forced && <span className="text-[10px] badge bg-orange-500/15 text-orange-300">Forcé</span>}
              {sub.is_gendered && <span className="text-[10px] badge bg-violet-500/15 text-violet-300">Genre</span>}
              <span className="text-[10px] text-gray-600">{sub.format}</span>
              <span className="text-[10px] text-gray-600">· {sub.source}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => onCreateTask(sub, 'translation')}
            disabled={starting === 'existing'}
            className="btn-primary !py-1.5 !px-3 !text-xs"
          >
            <Play className="w-3 h-3" /> Traduire
          </button>
          <div className="relative">
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="btn-ghost !p-1.5 text-gray-400 hover:text-gray-200"
            >
              <ChevronRight className="w-4 h-4" style={{ transform: menuOpen ? 'rotate(90deg)' : undefined, transition: 'transform 0.15s' }} />
            </button>
            {menuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                <div className="absolute right-0 top-full mt-1 z-20 w-56 bg-gray-800 border border-white/10 rounded-lg shadow-xl py-1">
                  <button className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/5 flex items-center gap-2" onClick={() => { onCreateTask(sub, 'improve'); setMenuOpen(false); }}>
                    <Sparkles className="w-3.5 h-3.5 text-brand-400" /> Améliorer
                  </button>
                  <button className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/5 flex items-center gap-2" onClick={() => { onSync(sub); setMenuOpen(false); }}>
                    <Clock className="w-3.5 h-3.5 text-violet-400" /> Resynchroniser
                  </button>
                  {isFRExisting && (
                    <button className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/5 flex items-center gap-2" onClick={() => { onCreateTask(sub, 'translation'); setMenuOpen(false); }}>
                      <ArrowRightLeft className="w-3.5 h-3.5 text-emerald-400" /> Refaire entièrement
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Shared components ──────────────────────────────────────────────────────

function MetaCard({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="glass-card p-3">
      <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider mb-0.5">{label}</p>
      <p className={`text-sm text-gray-200 ${mono ? 'font-mono break-all' : ''}`}>{value}</p>
    </div>
  );
}