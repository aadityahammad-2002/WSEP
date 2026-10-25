"""Apply WindSight shared-date and controlled-fetch behavior to a local WSEP checkout.
Safe, explicit source edits. Run from the repository root with: python apply_date_sync.py
"""
from pathlib import Path
import sys

root = Path.cwd()

def edit(relative, transforms):
    path=root/relative
    if not path.is_file():
        raise SystemExit(f'Missing {path}. Run this script from your WSEP project root.')
    original=path.read_text(encoding='utf-8')
    s=original
    for before,after in transforms:
        if before not in s:
            if after in s:
                print('Already applied:', relative, repr(before[:36]))
                continue
            raise SystemExit(f'Cannot find expected source in {relative}: {before[:160]!r}. File not changed.')
        s=s.replace(before,after,1)
    if s!=original:
        path.write_text(s,encoding='utf-8')
        print('Updated',relative)
    else: print('No changes needed', relative)

edit('frontend/src/api.ts', [
 ("const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL || '').replace(/\\/+$/, '');", """const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL || '').replace(/\\/+$/, '');

// Cache historical read-only responses per selected date / cutoff so changing tabs
// does not refetch the same server computations. Failed requests are never cached.
const historicalCache = new Map<string, Promise<unknown>>();
export function clearDataCache(scope: 'main' | 'history' | 'all' = 'all'): void {
  for (const key of historicalCache.keys()) {
    const isHistory = key.startsWith('history?');
    if (scope === 'all' || (scope === 'history' ? isHistory : !isHistory)) {
      historicalCache.delete(key);
    }
  }
}
"""),
 ("async function fetchJSON<T>(route: string, options?: RequestInit): Promise<T> {\n  const response = await fetch(`${API_ORIGIN}/api/${route}`, { ...options, headers: { Accept: 'application/json', ...options?.headers } });\n  if (!response.ok) {\n    let message = `${response.status}: ${response.statusText}`;\n    try { const error = await response.json(); message = typeof error.detail === 'string' ? error.detail : message; } catch { /* Non-JSON gateway errors are rendered as status text. */ }\n    throw new Error(message);\n  }\n  return response.json() as Promise<T>;\n}",
 """async function fetchJSON<T>(route: string, options?: RequestInit): Promise<T> {
  const read = async (): Promise<T> => {
    const response = await fetch(`${API_ORIGIN}/api/${route}`, {
      ...options, headers: { Accept: 'application/json', ...options?.headers }
    });
    if (!response.ok) {
      let message = `${response.status}: ${response.statusText}`;
      try { const error = await response.json(); message = typeof error.detail === 'string' ? error.detail : message; } catch { /* Gateway errors may be HTML. */ }
      throw new Error(message);
    }
    return response.json() as Promise<T>;
  };
  // Never cache mutations, status polling, current live forecasts or saved snapshots.
  const isHistorical = !options?.method && /^(analysis\\/|replay\\?|history\\?|metrics\\?)/.test(route);
  if (!isHistorical) return read();
  const previous = historicalCache.get(route) as Promise<T> | undefined;
  if (previous) return previous;
  const pending = read().catch((error: unknown) => {
    if (historicalCache.get(route) === pending) historicalCache.delete(route);
    throw error;
  });
  historicalCache.set(route, pending);
  return pending;
}"""),
 ("export const getMonthly = (time: string, day = \"2026-01-15\") => fetchJSON<Monthly>(`analysis/recent?day=${day}&hour=${time.slice(0,2)}&minute=${time.slice(3)}`);",
 "export const getMonthly = (time: string, day = '2026-01-15') => fetchJSON<Monthly>(`analysis/month?day=${day}&hour=${time.slice(0,2)}&minute=${time.slice(3)}`);"),
])

edit('frontend/src/ForecastWorkspace.tsx', [
 ("import { getLiveForecast, getReplayForecast, prepareForecast, saveLiveSnapshot, getSavedPredictions, getSavedPrediction, refreshSnapshotActuals, getStatus } from './api';",
  "import { clearDataCache, getLiveForecast, getReplayForecast, prepareForecast, saveLiveSnapshot, getSavedPredictions, getSavedPrediction, refreshSnapshotActuals, getStatus } from './api';"),
 ("export default function ForecastWorkspace({mode}:{mode:Mode}) {\n  const [date,setDate] = useState('2026-01-15');\n  const [decisionTime,setDecisionTime] = useState('09:50');",
 """export default function ForecastWorkspace({mode,date,decisionTime,onDateChange,onDecisionTimeChange,onDataImported}:{
  mode:Mode; date:string; decisionTime:string;
  onDateChange:(value:string)=>void; onDecisionTimeChange:(value:string)=>void;
  onDataImported:()=>void;
}) {"""),
 ("""      const [result,history,state] = await Promise.all([
        mode==='replay' ? getReplayForecast(date,decisionTime) : getLiveForecast(),
        getSavedPredictions(),getStatus(),
      ]);
      if (request!==requestId.current) return false;
      setReport(result);setSaved(history.items);setStatus(state);
      if (selected) { const refreshed = await getSavedPrediction(selected.id); setSelected(refreshed); }
      return true;""",
 """      // Replay loads only its historical forecast. Saved predictions belong to Live.
      if (mode === 'replay') {
        const result = await getReplayForecast(date, decisionTime);
        if (request!==requestId.current) return false;
        setReport(result);
        return true;
      }
      const [result,history,state] = await Promise.all([getLiveForecast(), getSavedPredictions(), getStatus()]);
      if (request!==requestId.current) return false;
      setReport(result);setSaved(history.items);setStatus(state);
      return true;"""),
 ("},[date,decisionTime,mode,selected?.id]);", "},[date,decisionTime,mode]);"),
 ("  useEffect(()=>{if(mode!=='live')return;void prepare();const id=window.setInterval(()=>void prepare(),30*60*1000);return()=>window.clearInterval(id);},[mode]);\n",
  "  // Do not start Elexon imports just by visiting Live; imports are user-initiated.\n"),
 ("          void refresh();", "          clearDataCache('main');\n          onDataImported();\n          void refresh();"),
 ("  },[status?.syncing,refresh]);", "  },[status?.syncing,refresh,onDataImported]);"),
 ("      const success=await refresh();", "      clearDataCache('main');\n      const success=await refresh();"),
 ("onChange={e=>setDate(e.target.value)}", "onChange={e=>onDateChange(e.target.value)}"),
 ("onChange={e=>setDecisionTime(e.target.value)}", "onChange={e=>onDecisionTimeChange(e.target.value)}"),
])

edit('frontend/src/HistoryPage.tsx', [
 ("import { getHistory, getStatus, importHistory } from './api';", "import { clearDataCache, getHistory, importHistory, getStatus } from './api';"),
 ("  const [draftStart,setDraftStart]=useState(dateForInput(-7));\n  const [draftEnd,setDraftEnd]=useState(dateForInput(-1));\n  const [range,setRange]=useState(()=>({start:dateForInput(-7),end:dateForInput(-1)}));",
  "  const [draftStart,setDraftStart]=useState('2026-01-01');\n  const [draftEnd,setDraftEnd]=useState('2026-01-31');\n  const [range,setRange]=useState(()=>({start:'2026-01-01',end:'2026-01-31'}));"),
 ("if(!st.syncing){setImporting(false);setNotice(st.errors.length?", "if(!st.syncing){clearDataCache('history');setImporting(false);setNotice(st.errors.length?"),
])

edit('frontend/src/App.tsx', [
 ("import { exportUrl, getComparison, getIntelligence, getMonthly, getRevisions, getStatus, prepareForecast } from './api';",
  "import { clearDataCache, exportUrl, getComparison, getIntelligence, getMonthly, getRevisions, getStatus, prepareForecast } from './api';"),
 ("const [date, setDate] = useState(ukYesterday);", "const [date, setDate] = useState('2026-01-15');"),
 ("  const [mobileOpen, setMobileOpen] = useState(false);", "  const [mobileOpen, setMobileOpen] = useState(false);\n  const [historyVisited, setHistoryVisited] = useState(false);"),
 ("  const activeRequest = useRef(0);", "  const activeRequest = useRef(0);\n  useEffect(() => { if(tab === 'history') setHistoryVisited(true); }, [tab]);\n  const onForecastImported = useCallback(() => { clearDataCache('main'); }, []);"),
 ("""    const [statusResult, dayResult, monthResult, intelligenceResult] = await Promise.allSettled([getStatus(), getComparison(date,time), getMonthly(time,date), getIntelligence(date,time)]);
    if (request !== activeRequest.current) return;
    if (statusResult.status === 'fulfilled') { setStatus(statusResult.value); setStatusError(''); }
    else setStatusError(statusResult.reason instanceof Error ? statusResult.reason.message : 'Could not connect to the API');
    if(dayResult.status === 'fulfilled') setDay(dayResult.value);
    else setDay(null);
    if(monthResult.status === 'fulfilled') setMonthly(monthResult.value);
    else setMonthly(null);
    setIntelligence(intelligenceResult.status === 'fulfilled' ? intelligenceResult.value : null);
    setLoading(false);
  }, [date, time]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if(!status?.syncing) return; const id = window.setInterval(() => void refresh(), 2800); return () => window.clearInterval(id); }, [status?.syncing, refresh]);
  async function requestSync() { setSyncRequest(true); try { await prepareForecast(date); await refresh(); } catch (e) { setStatusError(e instanceof Error ? e.message : 'Sync could not be started'); } finally { setSyncRequest(false); } }""",
 """    // Only fetch data used by the active analytics tab, never for hidden pages.
    const needsDay = tab === 'overview' || tab === 'records';
    const needsIntelligence = tab === 'overview' || tab === 'intelligence' || tab === 'records';
    if (!needsDay && !needsIntelligence) return;
    setLoading(true);
    const [statusResult, dayResult, monthResult, intelligenceResult] = await Promise.allSettled([
      getStatus(),
      needsDay ? getComparison(date,time) : Promise.resolve(null),
      tab === 'overview' ? getMonthly(time,date) : Promise.resolve(null),
      needsIntelligence ? getIntelligence(date,time) : Promise.resolve(null)
    ]);
    if (request !== activeRequest.current) return;
    if (statusResult.status === 'fulfilled') { setStatus(statusResult.value); setStatusError(''); }
    else setStatusError(statusResult.reason instanceof Error ? statusResult.reason.message : 'Could not connect to the API');
    if(needsDay) setDay(dayResult.status === 'fulfilled' ? dayResult.value : null);
    if(tab === 'overview') setMonthly(monthResult.status === 'fulfilled' ? monthResult.value : null);
    if(needsIntelligence) setIntelligence(intelligenceResult.status === 'fulfilled' ? intelligenceResult.value : null);
    setLoading(false);
  }, [date, time, tab]);

  useEffect(() => { if(tab === 'overview' || tab === 'intelligence' || tab === 'records') void refresh(); }, [refresh,tab]);
  useEffect(() => { if(!status?.syncing || (tab !== 'overview' && tab !== 'intelligence' && tab !== 'records')) return;
    const id = window.setInterval(() => void getStatus().then(s=>{
      setStatus(s);
      if(!s.syncing) { clearDataCache('main'); void refresh(); }
    }).catch(()=>{}), 3500);
    return () => window.clearInterval(id);
  }, [status?.syncing, tab, refresh]);
  async function requestSync() { setSyncRequest(true); try { await prepareForecast(date); await refresh(); } catch (e) { setStatusError(e instanceof Error ? e.message : 'Sync could not be started'); } finally { setSyncRequest(false); } }"""),
 ("{tab === 'replay' || tab === 'live' ? <ForecastWorkspace mode={tab}/> : tab === 'history' ? <HistoryPage/> : tab === 'methodology' ? <Methodology/> : tab === 'intelligence' ? <IntelligencePanel report={intelligence} loading={loading}/> : <>",
  """{historyVisited && <div style={{display:tab === 'history' ? 'block' : 'none'}}><HistoryPage/></div>}
      {tab === 'replay' || tab === 'live' ? <ForecastWorkspace mode={tab} date={date} decisionTime={time} onDateChange={setDate} onDecisionTimeChange={setTime} onDataImported={onForecastImported}/> : tab === 'history' ? null : tab === 'methodology' ? <Methodology/> : tab === 'intelligence' ? <IntelligencePanel report={intelligence} loading={loading}/> : <>"""),
 ("<input type=\"date\" min=\"2020-01-01\" max={ukYesterday()} value={date} onChange={e => setDate(e.target.value)} aria-label=\"Decision date\" />",
  "<input type=\"date\" value={date} readOnly aria-label=\"Shared decision date\" title=\"Change the shared date in Historical Replay\" />"),
 ("<select value={time} onChange={e => setTime(e.target.value)} aria-label=\"Decision cutoff\">",
  "<select value={time} disabled aria-label=\"Shared decision cutoff\">"),
 ("<span>Reconstructing what was known before purchase</span>", "<span>Shared with Historical Replay — change date and cutoff there</span>"),
 ("<span className=\"pill\">Recent 14 decisions</span>", "<span className=\"pill\">{(monthly?.metrics.total_days ?? 0)} decisions · selected month</span>"),
])

edit('backend/app/service.py', [
 ("from datetime import date, timedelta, datetime, timezone", "from datetime import date, timedelta, datetime, timezone\nfrom calendar import monthrange"),
 ("    def intelligence(self, day: date, hour: int = 9, minute: int = 50) -> dict:",
 """    def calendar_month(self, selected: date, hour: int = 9, minute: int = 50) -> dict:
        \"\"\"Aggregate each decision date in the selected calendar month (not just 14 days).\"\"\"
        days = [self.day(date(selected.year, selected.month, n), hour, minute, allow_any_day=True)
                for n in range(1, monthrange(selected.year, selected.month)[1] + 1)]
        present = [item for item in days if item['available']]
        observations = [point for item in present for point in item['points']]
        expected = sum(item['metrics']['expected'] for item in present)
        summary = metrics(observations, expected)
        summary.update({
            'available_days': len(present), 'total_days': len(days),
            'missing_days': [item['decision_date'] for item in days if not item['available']],
        })
        daily = [{'decision_date': item['decision_date'], 'delivery_date': item['delivery_date'],
                  'available': item['available'], **item['metrics']} for item in days]
        return {'metrics': summary, 'daily': daily, 'complete': len(present) == len(days)}

    def intelligence(self, day: date, hour: int = 9, minute: int = 50) -> dict:"""),
])

edit('backend/app/main.py', [
 ("@app.get('/api/analysis/recent')", """@app.get('/api/analysis/month')
def analysis_month(day: date, hour: int = Query(9, ge=0, le=23), minute: int = Query(50, ge=0, le=59)):
    valid_history_day(day)
    return service.calendar_month(day, hour, minute)


@app.get('/api/analysis/recent')"""),
])

print('\nDone. Commit updated files and deploy backend + frontend together.')
