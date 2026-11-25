import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { loadExternalActivities, refreshFigmaPage } from '../api/externalActivities';
import { replaceServiceChanges, type ActivityState } from '../data/activity';
import type { Project } from '../data/projects';

type RefreshState = { status: 'syncing' } | { status: 'error'; message: string };

export function useFigmaActivities(userId: number, project: Project | undefined, setProjects: Dispatch<SetStateAction<Project[]>>) {
  const projectId = project?.id;
  const url = project?.urls?.Figma;
  const key = JSON.stringify([userId, projectId, url]);
  const [lists, setLists] = useState<Record<string, ActivityState>>({});
  const [refreshes, setRefreshes] = useState<Partial<Record<string, RefreshState>>>({});
  const reads = useRef(new Map<string, AbortController>());
  const syncs = useRef(new Map<string, { key: string; controller: AbortController }>());
  const retryDeadlines = useRef(new Map<string, number>());

  const readList = useCallback(async (signal: AbortSignal) => {
    if (!projectId || !url) return;
    setLists(current => ({ ...current, [key]: { status: 'loading' } }));
    try {
      const incoming = await loadExternalActivities({ projectId, service: 'Figma', signal });
      if (signal.aborted) return;
      setProjects(current => current.map(item => item.id === projectId && item.urls?.Figma === url
        ? replaceServiceChanges(item, 'Figma', incoming) : item));
      setLists(current => ({ ...current, [key]: { status: 'ready' } }));
    } catch (error) {
      if (signal.aborted) return;
      setLists(current => ({ ...current, [key]: {
        status: 'error', error: error instanceof Error ? error.message : 'Figma 변경사항을 불러오지 못했어요.',
      } }));
    }
  }, [key, projectId, setProjects, url]);

  const reload = useCallback(() => {
    if (!projectId || !url || reads.current.has(key) || syncs.current.get(projectId)?.key === key) return;
    const controller = new AbortController();
    reads.current.set(key, controller);
    const release = () => {
      if (reads.current.get(key) === controller) reads.current.delete(key);
    };
    void Promise.resolve().then(() => {
      if (!controller.signal.aborted) return readList(controller.signal);
    }).finally(release);
    return () => { controller.abort(); release(); };
  }, [key, projectId, readList, url]);

  useEffect(() => {
    const activeReads = reads.current;
    const activeSyncs = syncs.current;
    return () => {
      activeReads.forEach(controller => controller.abort());
      activeSyncs.forEach(({ controller }) => controller.abort());
      activeReads.clear();
      activeSyncs.clear();
    };
  }, []);

  async function refresh() {
    if (!projectId || !url || reads.current.has(key) || syncs.current.has(projectId)) return;
    const controller = new AbortController();
    syncs.current.set(projectId, { key, controller });
    setRefreshes(current => ({ ...current, [key]: { status: 'syncing' } }));
    try {
      // Every click refreshes the displayed records, even during provider throttling.
      await readList(controller.signal);
      if (controller.signal.aborted) return;
      if ((retryDeadlines.current.get(key) ?? 0) <= Date.now()) {
        // Refresh means the newest records, never a saved pagination cursor.
        const result = await refreshFigmaPage(projectId, null, controller.signal);
        if (controller.signal.aborted) return;
        if ('message' in result) {
          if (result.retryAt !== undefined) retryDeadlines.current.set(key, result.retryAt);
          // Keep cached data visible; provider retry deadlines are internal state.
        } else {
          retryDeadlines.current.delete(key);
          await readList(controller.signal);
        }
      }
      if (!controller.signal.aborted) setRefreshes(current => ({ ...current, [key]: undefined }));
    } catch (error) {
      if (controller.signal.aborted) return;
      setRefreshes(current => ({ ...current, [key]: {
        status: 'error', message: error instanceof Error ? error.message : 'Figma 변경사항을 새로고침하지 못했어요.',
      } }));
    } finally {
      if (syncs.current.get(projectId)?.controller === controller) syncs.current.delete(projectId);
    }
  }

  const listState: ActivityState = !url ? { status: 'disconnected' } : lists[key] ?? { status: 'loading' };
  const state = refreshes[key];
  const syncing = state?.status === 'syncing';
  const error = state?.status === 'error' ? state.message : undefined;
  return {
    listState, syncing, notice: error, error,
    retryAt: undefined as number | undefined, hasMore: false,
    refreshDisabled: syncing || listState.status === 'loading',
    reload, refresh,
  };
}
