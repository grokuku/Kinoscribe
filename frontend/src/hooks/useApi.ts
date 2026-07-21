import { useEffect, useState, useCallback, useRef } from 'react';
import type { Film, Task, TaskProgress, GlossaryEntry, SubtitleLine } from '../types';
import { api } from '../api/client';

/** Generic fetch-on-mount hook */
function useFetch<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetcher();
      setData(result);
    } catch (e: any) {
      setError(e.message || 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, deps);

  useEffect(() => { refresh(); }, [refresh]);
  return { data, loading, error, refresh };
}

// ─── Domain hooks ────────────────────────────────────────────────────

export function useFilms() {
  return useFetch<Film[]>(() => api.listFilms());
}

export function useFilm(id: string) {
  return useFetch<Film>(() => api.getFilm(id), [id]);
}

export function useTasks(filters?: { limit?: number; status?: string; film_id?: number }) {
  return useFetch<Task[]>(() => api.fetchTasks(filters), [JSON.stringify(filters)]);
}

export function useTask(id: string) {
  return useFetch<Task>(() => api.getTask(id), [id]);
}

/**
 * Mutation hook to delete a task.
 * Returns a callback that performs the deletion.
 */
export function useDeleteTask() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deleteTask = useCallback(async (taskId: string) => {
    setLoading(true);
    setError(null);
    try {
      await api.deleteTask(taskId);
    } catch (e: any) {
      setError(e.message || 'Failed to delete task');
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);

  return { deleteTask, loading, error };
}

/**
 * Hook to fetch the content (SRT lines) of a completed task.
 */
export function useTaskContent(taskId: string | null) {
  return useFetch<SubtitleLine[] | null>(async () => {
    if (!taskId) return null;
    return api.fetchTaskContent(taskId);
  }, [taskId]);
}

/**
 * Polls task content (SRT lines) every `intervalMs` while the task is active.
 * Stops polling automatically when the task reaches a terminal state.
 * Returns the live lines, loading/error state, the current task status, and progress.
 */
export function useLiveTranslation(taskId: string, intervalMs = 2500) {
  const [lines, setLines] = useState<SubtitleLine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Use the existing polling hook for status/progress
  const { progress } = useTaskPolling(taskId, 2000);

  const isActive = progress !== null && !['completed', 'failed'].includes(progress.status);

  useEffect(() => {
    if (!taskId) return;

    let cancelled = false;

    const fetchLines = async () => {
      try {
        const content = await api.fetchTaskContent(taskId);
        if (!cancelled) {
          if (content) setLines(content);
          setError(null);
        }
      } catch (e: any) {
        if (!cancelled) setError(e.message || 'Failed to fetch content');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchLines(); // immediate first call

    // Only poll while the task is active
    if (isActive) {
      const interval = setInterval(fetchLines, intervalMs);
      return () => {
        cancelled = true;
        clearInterval(interval);
      };
    } else {
      return () => { cancelled = true; };
    }
  }, [taskId, isActive, intervalMs]);

  return {
    lines,
    loading,
    error,
    taskStatus: progress?.status ?? null,
    progress: progress?.progress_pct ?? 0,
    isActive,
  };
}

export function useGlossary(taskId: string) {
  return useFetch<GlossaryEntry[]>(() => api.getGlossary(taskId), [taskId]);
}

/**
 * Poll task progress every `intervalMs` until it reaches a terminal state.
 */
export function useTaskPolling(taskId: string, intervalMs = 2000) {
  const [progress, setProgress] = useState<TaskProgress | null>(null);
  const [polling, setPolling] = useState(true);
  const timerRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    setPolling(false);
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  useEffect(() => {
    if (!taskId) return;

    const poll = async () => {
      try {
        const p = await api.getTaskProgress(taskId);
        setProgress(p);
        if (p.status === 'completed' || p.status === 'failed') {
          stopPolling();
        }
      } catch {
        stopPolling();
      }
    };

    poll(); // immediate first call
    timerRef.current = window.setInterval(poll, intervalMs);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [taskId, intervalMs, stopPolling]);

  return { progress, polling, stopPolling };
}

/**
 * Poll all tasks at an interval.
 * Returns the tasks list, whether any are active, and a refresh function.
 */
export function useActiveTaskPolling(intervalMs = 3000) {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const timerRef = useRef<number | null>(null);

  const poll = useCallback(async () => {
    try {
      const result = await api.listTasks();
      setTasks(result);
    } catch {
      // ignore polling errors
    }
  }, []);

  useEffect(() => {
    poll(); // initial fetch
    timerRef.current = window.setInterval(poll, intervalMs);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [poll, intervalMs]);

  // Check if any tasks are still active
  const hasActive = (tasks ?? []).some(t =>
    ['analyzing_context', 'translating', 'refining', 'pending'].includes(t.status)
  );

  return { tasks, hasActive, refresh: poll };
}

/**
 * SSE-based real-time task updates.
 * Falls back to polling if SSE is not available.
 * Connects to /api/tasks/events and streams task progress.
 */
export function useTaskEvents() {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [connected, setConnected] = useState(false);
  const [hasActive, setHasActive] = useState(false);

  useEffect(() => {
    const eventSource = new EventSource('/api/tasks/events');

    eventSource.onopen = () => {
      setConnected(true);
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setTasks(data.tasks);
        setHasActive(data.active);
      } catch {
        // ignore parse errors
      }
    };

    eventSource.onerror = () => {
      setConnected(false);
      // EventSource will auto-reconnect
    };

    return () => {
      eventSource.close();
    };
  }, []);

  return { tasks, connected, hasActive };
}