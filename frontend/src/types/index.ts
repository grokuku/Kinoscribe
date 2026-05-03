export type { Setting } from './settings';

// ─── Film ─────────────────────────────────────────────────────

export interface Film {
  id: string;
  title: string;
  year: number | null;
  director: string | null;
  summary: string | null;
  source_language: string;
  target_language: string;
  characters: Character[];
  lore_summary: string | null;
  analysis_status: string;  // idle | analyzing | failed
  // Library / filesystem integration
  library_id: string | null;
  path: string | null;
  video_path: string | null;
  poster_path: string | null;
  has_existing_subs: boolean;
  created_at: string | null;
}

export interface ExistingSubtitle {
  filename: string;
  path: string;
  language: string | null;
  is_sdh: boolean;
  is_forced: boolean;
  is_gendered: boolean;
  format: string;
  source: 'scanner' | 'uploaded' | 'extracted' | 'transcribed';
}

export interface Character {
  name: string;
  gender: 'male' | 'female' | 'neutral' | 'unknown';
  description: string | null;
}

export interface FilmCreate {
  title: string;
  year?: number | null;
  director?: string | null;
  summary?: string | null;
  source_language?: string;
  target_language?: string;
}

// ─── Task ─────────────────────────────────────────────────────

export type TaskStatus =
  | 'pending'
  | 'analyzing_context'
  | 'translating'
  | 'refining'
  | 'extracting'
  | 'transcribing'
  | 'syncing'
  | 'rescanning'
  | 'completed'
  | 'failed';

export type TaskType =
  | 'translation'
  | 'improve'
  | 'sync'
  | 'transcription'
  | 'extract_subs'
  | 'extract_audio'
  | 'analyze';

export interface Task {
  id: string;
  film_id: string;
  task_type: TaskType;
  status: TaskStatus;
  source_filename: string;
  source_format: string;
  target_filename: string | null;
  progress_pct: number;
  error_message: string | null;
  created_at: string | null;
}

export interface TaskProgress {
  id: string;
  status: TaskStatus;
  progress_pct: number;
  error_message: string | null;
}

// ─── Glossary ─────────────────────────────────────────────────

export interface GlossaryEntry {
  source_term: string;
  target_term: string;
  notes: string | null;
}

// ─── Media Tracks ─────────────────────────────────────────────

export interface TrackInfo {
  index: number;
  codec: string;
  language: string;
  title?: string;
  default?: boolean;
  forced?: boolean;
  channels?: number;
  sample_rate?: string;
  width?: number;
  height?: number;
  format?: string;
  extractable?: boolean;
}

export interface ExtractedTrack {
  index: number;
  language: string;
  format: string;
  path: string;
  title?: string;
  default?: boolean;
  forced?: boolean;
}

export interface WorkFile {
  name: string;
  path: string;
  size: number;
}

export interface WorkFiles {
  audio: WorkFile[];
  subs: WorkFile[];
  whisper: WorkFile[];
  uploads: WorkFile[];
  sync: WorkFile[];
}