/**
 * API client — all calls go through here.
 * In dev, Vite proxies /api → backend:8000.
 * In prod (Docker), the same proxy or an nginx reverse-proxy handles it.
 */

const BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json();
}

import type { Film, FilmCreate } from '../types';

export const api = {
  // Films
  listFilms: () => request<Film[]>('/films/'),
  getFilm: (id: string) => request<Film>(`/films/${id}`),
  createFilm: (data: FilmCreate) =>
    request<Film>('/films/', { method: 'POST', body: JSON.stringify(data) }),
  deleteFilm: (id: string) =>
    request<void>(`/films/${id}`, { method: 'DELETE' }),
  getCharacters: (filmId: string) =>
    request<Character[]>(`/films/${filmId}/characters`),
  getFilmGlossary: (filmId: string) =>
    request<GlossaryEntry[]>(`/films/${filmId}/glossary`),
  getFilmLore: (filmId: string) =>
    request<{ lore_summary: string | null; task_id: string | null; task_status: string | null }>(`/films/${filmId}/lore`),
  getFilmPosterUrl: (filmId: string) => `/api/films/${filmId}/poster`,
  getFilmSubtitles: (filmId: string) =>
    request<ExistingSubtitle[]>(`/films/${filmId}/subtitles`),
  translateExistingSubtitle: (filmId: string, subtitlePath: string, sourceLanguage?: string) =>
    request<Task>(`/tasks/${filmId}/translate-existing`, {
      method: 'POST',
      body: JSON.stringify({ subtitle_path: subtitlePath, source_language: sourceLanguage }),
    }),
  analyzeFilm: (filmId: string) =>
    request<{ status: string; film_id: string }>(`/films/${filmId}/analyze`, { method: 'POST' }),
  transcribeFilm: (filmId: string, modelSize?: string, language?: string) =>
    request<{ status: string; film_id: string; model: string }>(`/films/${filmId}/transcribe?model_size=${modelSize || 'medium'}${language ? `&language=${language}` : ''}`, { method: 'POST' }),
  syncSubtitles: (filmId: string, subtitlePath: string, modelSize?: string) =>
    request<{ status: string; film_id: string }>(`/films/${filmId}/sync-subtitles?subtitle_path=${encodeURIComponent(subtitlePath)}&model_size=${modelSize || 'medium'}`, { method: 'POST' }),

  // Embedded tracks
  getFilmTracks: (filmId: string) =>
    request<{ film_id: string; video_path: string; audio: TrackInfo[]; subtitle: TrackInfo[]; video: TrackInfo[] }>(`/films/${filmId}/tracks`),
  extractSubtitles: (filmId: string, trackIndex?: number, extractAll?: boolean) =>
    request<{ status: string; film_id: string; tracks: ExtractedTrack[]; message?: string }>(`/films/${filmId}/extract-subtitles?track_index=${trackIndex ?? ''}&extract_all=${extractAll ?? true}`, { method: 'POST' }),
  extractAudio: (filmId: string, trackIndex?: number, language?: string) =>
    request<{ status: string; film_id: string; audio_path: string }>(`/films/${filmId}/extract-audio?track_index=${trackIndex ?? ''}&language=${language || 'und'}`, { method: 'POST' }),
  getWorkFiles: (filmId: string) =>
    request<{ film_id: string; files: WorkFiles }>(`/films/${filmId}/work-files`),
  cleanWorkFiles: (filmId: string, category?: string) =>
    request<{ status: string; film_id: string; category: string }>(`/films/${filmId}/work-files?category=${category || 'all'}`, { method: 'DELETE' }),

  // Tasks
  uploadSubtitle: (filmId: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<Task>(`/tasks/${filmId}/upload`, {
      method: 'POST',
      headers: {},
      body: form,
    });
  },
  startTranslation: (taskId: string) =>
    request<TaskProgress>(`/tasks/${taskId}/start`, { method: 'POST' }),
  listTasks: () => request<Task[]>('/tasks/'),
  getTask: (id: string) => request<Task>(`/tasks/${id}`),
  getTaskProgress: (id: string) => request<TaskProgress>(`/tasks/${id}/progress`),
  getGlossary: (taskId: string) =>
    request<GlossaryEntry[]>(`/tasks/${taskId}/glossary`),
  installSubtitle: (taskId: string) =>
    request<{ status: string; task_id: string; destination: string }>(`/tasks/${taskId}/install`, { method: 'POST' }),

  // Settings
  getSettings: () => request<Setting[]>('/settings/'),
  updateSettings: (updates: Record<string, string>) =>
    request<Setting[]>('/settings/', {
      method: 'PUT',
      body: JSON.stringify({ updates }),
    }),
  testOllama: () => request<{ ok: boolean; models?: string[]; error?: string }>('/settings/test-ollama', { method: 'POST' }),
  fetchOllamaModels: (baseUrl: string) =>
    request<{ ok: boolean; models: string[]; error?: string }>(
      `/settings/ollama-models?base_url=${encodeURIComponent(baseUrl)}`
    ),
};

import type { Character, Task, TaskProgress, GlossaryEntry, Setting, ExistingSubtitle, TrackInfo, ExtractedTrack, WorkFiles } from '../types';