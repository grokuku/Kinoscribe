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
  created_at: string | null;
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
  | 'completed'
  | 'failed';

export interface Task {
  id: string;
  film_id: string;
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