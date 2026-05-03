import { useState, useEffect, useCallback } from 'react';
import {
  Plus, FolderOpen, Trash2, Scan, HardDrive, Wifi,
  ChevronRight, RefreshCw, X, Plug, Loader2, Eye, EyeOff,
  CheckCircle2, AlertCircle, Film, Clock,
} from 'lucide-react';

// ─── Toast / Confirm system (shared with FilmDetailPage) ────────────────

type ToastType = 'success' | 'error' | 'info';
interface ToastMsg { id: number; type: ToastType; message: string; }
let _toastId = 0;
const _toastListeners = new Set<(t: ToastMsg[]) => void>();
let _toasts: ToastMsg[] = [];
function pushToast(type: ToastType, message: string) {
  const id = ++_toastId;
  _toasts = [..._toasts, { id, type, message }];
  _toastListeners.forEach(l => l([..._toasts]));
  setTimeout(() => { _toasts = _toasts.filter(t => t.id !== id); _toastListeners.forEach(l => l([..._toasts])); }, 4000);
}
let _resolveConfirm: ((v: boolean) => void) | null = null;
const _confirmListeners = new Set<(s: { open: boolean; message: string }) => void>();
let _confirmState = { open: false, message: '' };
function showConfirm(msg: string): Promise<boolean> {
  return new Promise(resolve => { _resolveConfirm = resolve; _confirmState = { open: true, message: msg }; _confirmListeners.forEach(l => l({ ..._confirmState })); });
}
function useToasts() {
  const [t, setT] = useState<ToastMsg[]>(_toasts);
  useEffect(() => { _toastListeners.add(setT); return () => { _toastListeners.delete(setT); }; }, []);
  return t;
}
function useConfirm() {
  const [s, setS] = useState(_confirmState);
  useEffect(() => { _confirmListeners.add(setS); return () => { _confirmListeners.delete(setS); }; }, []);
  return { ...s, yes: () => { _confirmState = { open: false, message: '' }; _confirmListeners.forEach(l => l({ ..._confirmState })); _resolveConfirm?.(true); _resolveConfirm = null; }, no: () => { _confirmState = { open: false, message: '' }; _confirmListeners.forEach(l => l({ ..._confirmState })); _resolveConfirm?.(false); _resolveConfirm = null; } };
}
const toast = { success: (m: string) => pushToast('success', m), error: (m: string) => pushToast('error', m), info: (m: string) => pushToast('info', m) };
const confirm = showConfirm;

// ─── Toast/Confirm renderers ──────────────────────────────────────────
function ToastBar() {
  const toasts = useToasts();
  if (!toasts.length) return null;
  return <div className="fixed top-4 right-4 z-[100] space-y-2 max-w-sm">{toasts.map(t => (
    <div key={t.id} className={`flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium ${t.type === 'error' ? 'bg-red-500/90 text-white' : t.type === 'success' ? 'bg-emerald-500/90 text-white' : 'bg-brand-500/90 text-white'}`}>
      <span className="flex-1">{t.message}</span>
      <button onClick={() => { _toasts = _toasts.filter(x => x.id !== t.id); _toastListeners.forEach(l => l([..._toasts])); }} className="opacity-70 hover:opacity-100"><X className="w-3.5 h-3.5" /></button>
    </div>))}</div>;
}
function ConfirmDlg() {
  const { open, message, yes, no } = useConfirm();
  if (!open) return null;
  return <div className="fixed inset-0 z-[99] flex items-center justify-center bg-black/60"><div className="bg-gray-800 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl border border-white/10">
    <p className="text-white text-sm mb-6 whitespace-pre-line">{message}</p>
    <div className="flex gap-3 justify-end"><button onClick={no} className="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition">Annuler</button><button onClick={yes} className="px-4 py-2 text-sm rounded-lg bg-brand-500 text-white hover:bg-brand-600 transition">Confirmer</button></div>
  </div></div>;
}

// ─── Types ─────────────────────────────────────────────────────────────

interface LibrarySource {
  id: string;
  library_id: string;
  source_type: 'local' | 'ssh' | 'smb' | 'cifs';
  path: string;
  ssh_host: string | null;
  ssh_port: number | null;
  ssh_username: string | null;
  ssh_auth_type: 'key' | 'password' | null;
  ssh_private_key_path: string | null;
  ssh_password: string | null;
  ssh_remote_path: string | null;
  enabled: boolean;
  scan_depth: number;
  last_scan_at: string | null;
  scan_status: 'idle' | 'scanning' | 'error';
  scan_error: string | null;
  mount_status: 'unmounted' | 'mounted' | 'error' | 'unsupported';
  mount_point: string | null;
  mount_error: string | null;
}

interface Library {
  id: string;
  name: string;
  description: string | null;
  sources: LibrarySource[];
  created_at: string | null;
  updated_at: string | null;
}

interface ScanProgressData {
  library_id: string;
  status: 'idle' | 'scanning' | 'completed' | 'error';
  total_dirs: number;
  scanned_dirs: number;
  current_dir: string;
  films_found: number;
  films_created: number;
  films_updated: number;
  errors: string[];
  started_at: string | null;
  completed_at: string | null;
}

// ─── Source type config ───────────────────────────────────────────────

const SOURCE_TYPES = [
  { value: 'local', label: 'Dossier local', icon: HardDrive, desc: 'Répertoire sur le serveur local' },
  { value: 'ssh', label: 'SSH distant', icon: Wifi, desc: 'Serveur distant via SSH/SFTP — montage automatique via sshfs' },
  { value: 'smb', label: 'SMB/CIFS', icon: HardDrive, desc: 'Partage Windows / NAS — montage automatique via cifs-utils' },
] as const;

// ─── API helpers ────────────────────────────────────────────────────────

const API = '/api/libraries';
async function api_GET(path: string) { const r = await fetch(`/api${path}`); if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); }
async function api_POST(path: string, body?: any) { const r = await fetch(`/api${path}`, { method: 'POST', headers: body ? {'Content-Type': 'application/json'} : undefined, body: body ? JSON.stringify(body) : undefined }); if (r.status === 204) return; if (!r.ok) { const t = await r.text(); throw new Error(t); } return r.json(); }
async function api_PUT(path: string, body: any) { const r = await fetch(`/api${path}`, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) }); if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); }
async function api_DELETE(path: string) { const r = await fetch(`/api${path}`, { method: 'DELETE' }); if (r.status !== 204 && !r.ok) throw new Error(`API ${r.status}`); }

// ─── Page ───────────────────────────────────────────────────────────────

export default function LibrariesPage() {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [expandedLib, setExpandedLib] = useState<string | null>(null);
  const [showAddSource, setShowAddSource] = useState<string | null>(null);
  const [progressMap, setProgressMap] = useState<Record<string, ScanProgressData>>({});

  const loadLibraries = useCallback(async () => {
    setLoading(true); setError(null);
    try { setLibraries(await api_GET('/libraries/')); }
    catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  // Poll all scan progress
  useEffect(() => {
    loadLibraries();
    const timer = setInterval(async () => {
      try {
        const all = await api_GET('/libraries/scan-progress/all') as Record<string, ScanProgressData>;
        setProgressMap(all);
      } catch { /* ignore */ }
    }, 2000);
    return () => clearInterval(timer);
  }, [loadLibraries]);

  // Refresh libraries when scans complete
  useEffect(() => {
    const anyCompleted = Object.values(progressMap).some(p => p.status === 'completed');
    if (anyCompleted) loadLibraries();
  }, [progressMap, loadLibraries]);

  async function handleCreate(name: string, description?: string) {
    try { await api_POST('/libraries/', { name, description }); await loadLibraries(); setShowCreate(false); toast.success('Bibliothèque créée'); }
    catch (e: any) { toast.error('Erreur : ' + e.message); }
  }
  async function handleDelete(id: string) {
    if (!await confirm('Supprimer cette bibliothèque et tous les films qu\'elle contient ?')) return;
    try { await api_DELETE(`/libraries/${id}?delete_films=true`); await loadLibraries(); if (expandedLib === id) setExpandedLib(null); toast.success('Bibliothèque supprimée'); }
    catch (e: any) { toast.error('Erreur : ' + e.message); }
  }
  async function handleAddSource(libraryId: string, data: any) {
    try { await api_POST(`/libraries/${libraryId}/sources`, data); await loadLibraries(); setShowAddSource(null); toast.success('Source ajoutée'); }
    catch (e: any) { toast.error('Erreur : ' + e.message); }
  }
  async function handleDeleteSource(libraryId: string, sourceId: string) {
    if (!await confirm('Supprimer cette source et les films qu\'elle contient ?')) return;
    try { await api_DELETE(`/libraries/${libraryId}/sources/${sourceId}?delete_films=true`); await loadLibraries(); toast.success('Source supprimée'); }
    catch (e: any) { toast.error('Erreur : ' + e.message); }
  }
  async function handleScan(libraryId: string) {
    try { await api_POST(`/libraries/${libraryId}/scan`); toast.info('Scan lancé'); }
    catch (e: any) { toast.error('Erreur : ' + e.message); }
  }

  if (loading && libraries.length === 0) return (
    <div className="flex items-center justify-center py-32"><div className="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" /></div>
  );
  if (error && libraries.length === 0) return <div className="flex items-center justify-center py-32 text-red-400">Erreur : {error}</div>;

  return (
    <div className="animate-fade-in">
      <ToastBar />
      <ConfirmDlg />
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-100 tracking-tight">Bibliothèques</h1>
          <p className="text-sm text-gray-500 mt-1">Ajoutez vos dossiers de films — local ou SSH — Kinoscribe les scanne automatiquement</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="btn-primary self-start sm:self-auto"><Plus className="w-4 h-4" /> Ajouter une bibliothèque</button>
      </div>

      {libraries.length === 0 && !showCreate && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="flex items-center justify-center w-20 h-20 rounded-3xl bg-white/[0.03] mb-6"><FolderOpen className="w-10 h-10 text-gray-700" /></div>
          <h2 className="text-xl font-semibold text-gray-400 mb-2">Aucune bibliothèque</h2>
          <p className="text-sm text-gray-600 max-w-md mb-6">Créez une bibliothèque, ajoutez vos dossiers de films, et lancez un scan.</p>
          <button onClick={() => setShowCreate(true)} className="btn-primary"><Plus className="w-4 h-4" /> Ajouter une bibliothèque</button>
        </div>
      )}

      <div className="space-y-4">
        {libraries.map((lib) => {
          const prog = progressMap[lib.id];
          const isScanning = prog?.status === 'scanning';
          const pct = prog?.total_dirs ? Math.round((prog.scanned_dirs / prog.total_dirs) * 100) : 0;

          return (
            <div key={lib.id} className="glass-card overflow-hidden">
              {/* Header */}
              <div className="px-5 py-4 flex items-center justify-between cursor-pointer hover:bg-white/[0.02] transition-colors" onClick={() => setExpandedLib(expandedLib === lib.id ? null : lib.id)}>
                <div className="flex items-center gap-3 min-w-0">
                  <div className="flex-shrink-0 flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500/20 to-orange-500/20">
                    <FolderOpen className="w-5 h-5 text-amber-400" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-base font-bold text-gray-100 truncate">{lib.name}</h3>
                    {lib.description && <p className="text-xs text-gray-500 mt-0.5 truncate">{lib.description}</p>}
                  </div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <span className="text-xs text-gray-600">{lib.sources.length} source{lib.sources.length !== 1 ? 's' : ''}</span>
                  {/* Scan status badge */}
                  {isScanning && (
                    <span className="badge bg-brand-500/15 text-brand-300"><RefreshCw className="w-3 h-3 animate-spin" /> Scan… {pct}%</span>
                  )}
                  {prog?.status === 'completed' && (
                    <span className="badge bg-emerald-500/15 text-emerald-300"><CheckCircle2 className="w-3 h-3" /> {prog.films_created + prog.films_updated} films</span>
                  )}
                  <button onClick={(e) => { e.stopPropagation(); handleDelete(lib.id); }} className="btn-ghost text-gray-600 hover:text-red-400 !p-1.5" title="Supprimer"><Trash2 className="w-4 h-4" /></button>
                  <ChevronRight className={`w-5 h-5 text-gray-500 transition-transform duration-200 ${expandedLib === lib.id ? 'rotate-90' : ''}`} />
                </div>
              </div>

              {/* Progress bar (visible while scanning) */}
              {isScanning && (
                <div className="px-5 pb-2">
                  <div className="scan-progress-bar">
                    <div className="scan-progress-fill" style={{ width: `${pct}%` }} />
                  </div>
                  <div className="flex items-center justify-between mt-1.5">
                    <span className="text-[11px] text-gray-500">{prog.scanned_dirs}/{prog.total_dirs} dossiers — <span className="text-gray-300">{prog.current_dir || '…'}</span></span>
                    <span className="text-[11px] text-gray-500">{prog.films_found} films trouvés</span>
                  </div>
                </div>
              )}

              {/* Scan result summary (visible after completion) */}
              {prog?.status === 'completed' && prog.completed_at && (
                <div className="px-5 py-2 bg-emerald-500/5 border-t border-emerald-500/10 text-xs text-emerald-300/80">
                  <CheckCircle2 className="w-3.5 h-3.5 inline mr-1.5" />
                  Scan terminé — {prog.films_created} créé{prog.films_created > 1 ? 's' : ''}, {prog.films_updated} mis à jour
                  {prog.errors.length > 0 && <span className="text-yellow-400 ml-2">({prog.errors.length} erreur{prog.errors.length > 1 ? 's' : ''})</span>}
                </div>
              )}

              {/* Expanded content */}
              {expandedLib === lib.id && (
                <div className="border-t border-white/[0.04] px-5 py-4 space-y-4 animate-fade-in">
                  {lib.sources.length === 0 && (
                    <p className="text-sm text-gray-600 text-center py-4">Aucun dossier source — ajoutez-en un ci-dessous</p>
                  )}
                  {lib.sources.map((source) => (
                    <SourceRow key={source.id} source={source} onDelete={() => handleDeleteSource(lib.id, source.id)} />
                  ))}

                  {showAddSource === lib.id ? (
                    <AddSourceForm libraryId={lib.id} onSubmit={(data: any) => handleAddSource(lib.id, data)} onCancel={() => setShowAddSource(null)} />
                  ) : (
                    <button onClick={() => setShowAddSource(lib.id)} className="btn-secondary w-full justify-center"><Plus className="w-4 h-4" /> Ajouter un dossier source</button>
                  )}

                  <div className="flex items-center gap-3 pt-2 border-t border-white/[0.04]">
                    <button onClick={() => handleScan(lib.id)} disabled={isScanning || lib.sources.length === 0} className="btn-primary disabled:opacity-40">
                      {isScanning ? <><RefreshCw className="w-4 h-4 animate-spin" /> Scan en cours…</> : <><Scan className="w-4 h-4" /> Scanner</>}
                    </button>
                    <span className="text-xs text-gray-600">Détecte les films, .nfo, posters et sous-titres</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {showCreate && <CreateLibraryModal onSubmit={handleCreate} onClose={() => setShowCreate(false)} />}
    </div>
  );
}

// ─── Source Row ──────────────────────────────────────────────────────────

function SourceRow({ source, onDelete }: { source: LibrarySource; onDelete: () => void }) {
  const Icon = source.source_type === 'ssh' ? Wifi : HardDrive;
  const isErr = source.scan_status === 'error';
  const isMounted = source.mount_status === 'mounted';
  const isMountError = source.mount_status === 'error';
  const canMount = source.source_type !== 'local';
  const displayPath = source.source_type === 'ssh'
    ? `${source.ssh_username || 'user'}@${source.ssh_host}:${source.ssh_remote_path || source.path}`
    : source.source_type === 'smb' || source.source_type === 'cifs'
    ? source.path
    : source.path;

  return (
    <div className={`flex flex-col gap-2 p-3 rounded-xl bg-white/[0.02] border ${isErr ? 'border-red-500/20' : 'border-white/[0.04]'}`}>
      <div className="flex items-start gap-3">
        <div className={`flex-shrink-0 flex items-center justify-center w-9 h-9 rounded-lg ${source.source_type === 'ssh' ? 'bg-violet-500/15' : source.source_type === 'smb' || source.source_type === 'cifs' ? 'bg-blue-500/15' : 'bg-emerald-500/15'}`}>
          <Icon className={`w-4 h-4 ${source.source_type === 'ssh' ? 'text-violet-400' : source.source_type === 'smb' || source.source_type === 'cifs' ? 'text-blue-400' : 'text-emerald-400'}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-200 truncate">{displayPath}</span>
            {source.ssh_port && source.ssh_port !== 22 && source.source_type === 'ssh' && <span className="text-xs text-gray-500">:{source.ssh_port}</span>}
            {source.ssh_auth_type && <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400">{source.ssh_auth_type === 'key' ? '🔑 Clé' : '🔒 MDP'}</span>}
          </div>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className="text-[10px] font-medium uppercase tracking-wider text-gray-600">{source.source_type}</span>
            {!source.enabled && <span className="text-[10px] text-yellow-500 uppercase">Désactivé</span>}
            {source.scan_status === 'scanning' && <span className="text-[10px] text-brand-400">Scan…</span>}
            {isErr && <span className="text-[10px] text-red-400">⚠️ {source.scan_error?.slice(0, 60)}</span>}
            {source.last_scan_at && source.scan_status === 'idle' && !isErr && (
              <span className="text-[10px] text-gray-600">{new Date(source.last_scan_at).toLocaleString('fr-FR')}</span>
            )}
          </div>
        </div>
        <button onClick={onDelete} className="btn-ghost text-gray-600 hover:text-red-400 !p-1.5 flex-shrink-0" title="Supprimer"><X className="w-4 h-4" /></button>
      </div>
      {/* Mount status row (informational only — mounting is automatic) */}
      {canMount && (
        <div className="flex items-center gap-2 pl-12">
          {isMounted ? (
            <span className="text-[10px] font-medium text-emerald-400 flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> Monté
            </span>
          ) : isMountError ? (
            <span className="text-[10px] font-medium text-red-400">⚠️ Erreur montage : {source.mount_error?.slice(0, 80)}</span>
          ) : (
            <span className="text-[10px] text-gray-500">Sera monté automatiquement au scan</span>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Add Source Form ──────────────────────────────────────────────────────

function AddSourceForm({ libraryId, onSubmit, onCancel }: { libraryId: string; onSubmit: (data: any) => void; onCancel: () => void }) {
  const [sourceType, setSourceType] = useState<'local' | 'ssh' | 'smb'>('local');
  const [path, setPath] = useState('');
  const [sshHost, setSshHost] = useState('');
  const [sshPort, setSshPort] = useState(22);
  const [sshUsername, setSshUsername] = useState('');
  const [sshAuthType, setSshAuthType] = useState<'key' | 'password'>('key');
  const [sshPrivateKeyPath, setSshPrivateKeyPath] = useState('');
  const [sshPassword, setSshPassword] = useState('');
  const [sshRemotePath, setSshRemotePath] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ connected: boolean; error?: string; entries?: string[]; path_exists?: boolean; path_is_dir?: boolean; total_entries?: number } | null>(null);

  const canSubmit = sourceType === 'local' ? path.trim() : sourceType === 'smb' ? path.trim() : sshHost.trim() && sshRemotePath.trim();

  async function handleTestSsh() {
    setTesting(true); setTestResult(null);
    try {
      const res = await fetch('/api/libraries/test-ssh', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: sshHost, port: sshPort, username: sshUsername || 'root', auth_type: sshAuthType, private_key_path: sshAuthType === 'key' ? sshPrivateKeyPath : null, password: sshAuthType === 'password' ? sshPassword : null, remote_path: sshRemotePath }),
      });
      setTestResult(await res.json());
    } catch (e: any) { setTestResult({ connected: false, error: e.message }); }
    finally { setTesting(false); }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); if (!canSubmit) return;
    const data: any = { source_type: sourceType, path: sourceType === 'local' ? path.trim() : sourceType === 'smb' ? path.trim() : `ssh://${sshUsername || 'root'}@${sshHost}:${sshPort}${sshRemotePath}`, scan_depth: 2 };
    if (sourceType === 'ssh') {
      data.ssh_host = sshHost; data.ssh_port = sshPort; data.ssh_username = sshUsername || 'root';
      data.ssh_auth_type = sshAuthType; data.ssh_private_key_path = sshAuthType === 'key' ? sshPrivateKeyPath : null;
      data.ssh_password = sshAuthType === 'password' ? sshPassword : null; data.ssh_remote_path = sshRemotePath;
    } else if (sourceType === 'smb') {
      data.ssh_username = sshUsername || 'guest';
      data.ssh_password = sshPassword || null;
      // For SMB, 'path' is the UNC path (e.g. //192.168.1.100/Films)
    }
    onSubmit(data);
  }

  return (
    <form onSubmit={handleSubmit} className="glass-card p-5 space-y-4 border border-brand-500/30">
      <h4 className="text-sm font-semibold text-gray-200">Ajouter un dossier source</h4>
      <div className="flex gap-2">
        {SOURCE_TYPES.map((t) => (
          <button key={t.value} type="button" onClick={() => { setSourceType(t.value as any); setTestResult(null); }}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${sourceType === t.value ? 'bg-brand-500/20 text-brand-300 ring-1 ring-brand-500/40' : 'bg-white/[0.03] text-gray-500 hover:text-gray-300 hover:bg-white/[0.05]'}`}>
            <t.icon className="w-4 h-4" />{t.label}
          </button>
        ))}
      </div>

      {sourceType === 'local' && (
        <div>
          <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Chemin du dossier</label>
          <input type="text" value={path} onChange={(e) => setPath(e.target.value)} placeholder="/mnt/media/Films" className="input-field" />
          <p className="text-xs text-gray-600 mt-1">Chemin absolu sur le serveur</p>
        </div>
      )}

      {sourceType === 'ssh' && (
        <div className="space-y-3">
          <div className="p-3 rounded-lg bg-violet-500/5 border border-violet-500/10">
            <p className="text-xs text-violet-300/80 flex items-center gap-1.5"><Wifi className="w-3.5 h-3.5" />Connexion SFTP — les fichiers sont lus directement via SSH</p>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2"><label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Hôte *</label><input type="text" value={sshHost} onChange={(e) => setSshHost(e.target.value)} placeholder="192.168.1.100" className="input-field" /></div>
            <div><label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Port</label><input type="number" value={sshPort} onChange={(e) => setSshPort(parseInt(e.target.value) || 22)} className="input-field" /></div>
          </div>
          <div><label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Utilisateur</label><input type="text" value={sshUsername} onChange={(e) => setSshUsername(e.target.value)} placeholder="root" className="input-field" /></div>
          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Authentification</label>
            <div className="flex gap-2">
              <button type="button" onClick={() => { setSshAuthType('key'); setTestResult(null); }}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${sshAuthType === 'key' ? 'bg-violet-500/20 text-violet-300 ring-1 ring-violet-500/30' : 'bg-white/[0.03] text-gray-500'}`}>🔑 Clé SSH</button>
              <button type="button" onClick={() => { setSshAuthType('password'); setTestResult(null); }}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${sshAuthType === 'password' ? 'bg-violet-500/20 text-violet-300 ring-1 ring-violet-500/30' : 'bg-white/[0.03] text-gray-500'}`}>🔒 Mot de passe</button>
            </div>
          </div>
          {sshAuthType === 'key' ? (
            <div><label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Chemin de la clé privée <span className="text-gray-600">(sur le serveur Kinoscribe)</span></label><input type="text" value={sshPrivateKeyPath} onChange={(e) => setSshPrivateKeyPath(e.target.value)} placeholder="/app/data/ssh_keys/id_rsa" className="input-field font-mono text-sm" /></div>
          ) : (
            <div><label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Mot de passe</label>
              <div className="relative"><input type={showPassword ? 'text' : 'password'} value={sshPassword} onChange={(e) => setSshPassword(e.target.value)} placeholder="Mot de passe SSH" className="input-field pr-10" />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-2 top-1/2 -translate-y-1/2 btn-ghost !p-1">{showPassword ? <EyeOff className="w-4 h-4 text-gray-500" /> : <Eye className="w-4 h-4 text-gray-500" />}</button></div></div>
          )}
          <div><label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Chemin distant *</label><input type="text" value={sshRemotePath} onChange={(e) => setSshRemotePath(e.target.value)} placeholder="/mnt/media/Films" className="input-field font-mono text-sm" /></div>
          <div className="pt-2 space-y-3">
            <button type="button" onClick={handleTestSsh} disabled={testing || !sshHost.trim()} className="btn-secondary w-full disabled:opacity-40">
              {testing ? <><Loader2 className="w-4 h-4 animate-spin" /> Test en cours…</> : <><Plug className="w-4 h-4" /> Tester la connexion</>}
            </button>
            {testResult && (
              <div className={`p-3 rounded-lg border text-sm ${testResult.connected ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300' : 'bg-red-500/10 border-red-500/20 text-red-300'}`}>
                {testResult.connected ? (
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 font-medium"><CheckCircle2 className="w-4 h-4" /> Connexion réussie !</div>
                    {testResult.path_exists !== undefined && (
                      <div className="text-xs mt-1">{testResult.path_exists
                        ? (testResult.path_is_dir ? <span>✅ Dossier <code className="bg-white/10 px-1 rounded">{sshRemotePath}</code> — {testResult.total_entries || 0} entrées</span> : <span>⚠️ Le chemin existe mais n'est pas un dossier</span>)
                        : <span>⚠️ Le dossier n'existe pas</span>}
                      </div>
                    )}
                    {testResult.entries && testResult.entries.length > 0 && (
                      <div className="text-xs text-emerald-400/70">Contenu : {testResult.entries.slice(0, 8).join(', ')}{testResult.entries.length > 8 ? `… +${testResult.entries.length - 8}` : ''}</div>
                    )}
                  </div>
                ) : (
                  <div className="flex items-start gap-2"><AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" /><div><div className="font-medium">Échec</div><div className="text-xs mt-0.5 opacity-80">{testResult.error}</div></div></div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {sourceType === 'smb' && (
        <div className="space-y-3">
          <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/10">
            <p className="text-xs text-blue-300/80 flex items-center gap-1.5"><HardDrive className="w-3.5 h-3.5" />Partage SMB/CIFS — monté automatiquement dans le conteneur Docker</p>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Chemin UNC *</label>
            <input type="text" value={path} onChange={(e) => setPath(e.target.value)} placeholder="//192.168.1.100/Films" className="input-field font-mono text-sm" />
            <p className="text-xs text-gray-600 mt-1">Format : //serveur/partage (ex: //nas.local/Films)</p>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Sous-dossier <span className="text-gray-600">(optionnel)</span></label>
            <input type="text" value={sshRemotePath} onChange={(e) => setSshRemotePath(e.target.value)} placeholder="/Films" className="input-field font-mono text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Utilisateur</label><input type="text" value={sshUsername} onChange={(e) => setSshUsername(e.target.value)} placeholder="guest" className="input-field" /></div>
            <div><label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Mot de passe</label>
              <div className="relative"><input type={showPassword ? 'text' : 'password'} value={sshPassword} onChange={(e) => setSshPassword(e.target.value)} placeholder="Mot de passe SMB" className="input-field pr-10" />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-2 top-1/2 -translate-y-1/2 btn-ghost !p-1">{showPassword ? <EyeOff className="w-4 h-4 text-gray-500" /> : <Eye className="w-4 h-4 text-gray-500" />}</button></div></div>
          </div>
        </div>
      )}

      <div className="flex justify-end gap-3 pt-2">
        <button type="button" onClick={onCancel} className="btn-secondary">Annuler</button>
        <button type="submit" disabled={!canSubmit} className="btn-primary disabled:opacity-40"><Plus className="w-4 h-4" /> Ajouter</button>
      </div>
    </form>
  );
}

// ─── Create Library Modal ────────────────────────────────────────────

function CreateLibraryModal({ onSubmit, onClose }: { onSubmit: (name: string, description?: string) => void; onClose: () => void }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  function handleSubmit(e: React.FormEvent) { e.preventDefault(); if (!name.trim()) return; onSubmit(name.trim(), description.trim() || undefined); }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="glass-card p-6 w-full max-w-md animate-slide-up shadow-2xl shadow-black/50">
        <div className="flex items-center justify-between mb-5"><h2 className="text-lg font-bold text-gray-100">Nouvelle bibliothèque</h2><button onClick={onClose} className="btn-ghost !p-1.5"><X className="w-5 h-5" /></button></div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div><label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Nom *</label><input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Films, Séries, Documentaires…" className="input-field" autoFocus /></div>
          <div><label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Description</label><textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} placeholder="Bibliothèque de films Jellyfin…" className="input-field resize-none" /></div>
          <div className="flex justify-end gap-3"><button type="button" onClick={onClose} className="btn-secondary">Annuler</button><button type="submit" disabled={!name.trim()} className="btn-primary disabled:opacity-40">Créer</button></div>
        </form>
      </div>
    </div>
  );
}