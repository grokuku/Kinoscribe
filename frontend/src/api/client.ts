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

// ─── Films ───────────────────────────────────────────────────

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

  // Tasks
  uploadSubtitle: (filmId: string, file: File, sourceLanguage = 'en') => {
    const form = new FormData();
    form.append('file', file);
    return request<Task>(`/tasks/${filmId}/upload?source_language=${sourceLanguage}`, {
      method: 'POST',
      headers: {}, // let browser set Content-Type for multipart
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
  // Settings
  getSettings: () => request<Setting[]>('/settings/'),
  updateSettings: (updates: Record<string, string>) =>
    request<Setting[]>('/settings/', {
      method: 'PUT',
      body: JSON.stringify({ updates }),
    }),
  testOllama: () => request<{ ok: boolean; models?: string[]; error?: string }>('/settings/test-ollama', { method: 'POST' }),
};

// Re-export types used in signatures
import type { Character, Task, TaskProgress, GlossaryEntry, Setting } from '../types';