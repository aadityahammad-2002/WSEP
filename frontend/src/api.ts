import type { Comparison, Intelligence, Monthly, Revision, Status, PredictionDetails, PredictionItem } from './types';

async function fetchJSON<T>(route: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/${route}`, { ...options, headers: { Accept: 'application/json', ...options?.headers } });
  if (!response.ok) {
    let message = `${response.status}: ${response.statusText}`;
    try { const error = await response.json(); message = typeof error.detail === 'string' ? error.detail : message; } catch { /* Non-JSON gateway errors are rendered as status text. */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const getStatus = () => fetchJSON<Status>('status');
export const getComparison = (date: string, time: string) => fetchJSON<Comparison>(`analysis/day?day=${date}&hour=${time.slice(0,2)}&minute=${time.slice(3)}`);
export const getMonthly = (time: string, day = "2026-01-15") => fetchJSON<Monthly>(`analysis/recent?day=${day}&hour=${time.slice(0,2)}&minute=${time.slice(3)}`);
export const getRevisions = (date: string, time: string, start: string) => fetchJSON<{ versions: Revision[] }>(`analysis/versions?day=${date}&hour=${time.slice(0,2)}&minute=${time.slice(3)}&start=${encodeURIComponent(start)}`);
export const startSync = () => fetchJSON<Status>('sync', { method: 'POST' });
export const exportUrl = (date: string, time: string) => `/api/analysis/export.csv?day=${date}&hour=${time.slice(0,2)}&minute=${time.slice(3)}`;

export const getIntelligence = (date: string, time: string) => fetchJSON<Intelligence>(`analysis/intelligence?day=${date}&hour=${time.slice(0,2)}&minute=${time.slice(3)}`);

export const getReplayForecast = (date: string, time: string) => fetchJSON<Intelligence>(`replay?day=${date}&hour=${time.slice(0,2)}&minute=${time.slice(3)}`);
export const getLiveForecast = () => fetchJSON<Intelligence & {gate_closed:boolean;current_time:string;trading_note:string}>('live');
export const prepareForecast = (date: string) => fetchJSON<Status & {started:boolean}>(`prepare?day=${date}`,{method:'POST'});
export const saveLiveSnapshot = (cutoff:string) => fetchJSON<{id:string}>(`live/snapshot?cutoff=${encodeURIComponent(cutoff)}`,{method:'POST'});
export const getSavedPredictions = () => fetchJSON<{items:PredictionItem[]}>('predictions');
export const getSavedPrediction = (id:string) => fetchJSON<PredictionDetails>(`predictions/${id}`);
export const refreshSnapshotActuals = (id:string) => fetchJSON<Status & {started:boolean}>(`predictions/${id}/refresh-actual`,{method:'POST'});

import type { HistoryResult } from './types';
export const getHistory = (from: string, to: string, page: number, time: string) =>
  fetchJSON<HistoryResult>(`history?start=${from}&end=${to}&page=${page}&page_size=5&hour=${time.slice(0,2)}&minute=${time.slice(3)}`);
export const importHistory = (from: string, to: string) =>
  fetchJSON<Status & {started:boolean}>(`history/prepare?start=${from}&end=${to}`, {method:'POST'});
