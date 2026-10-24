import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, ArrowRight, CalendarDays, CheckCircle2, Clock3, Database, Eye, RefreshCw, ShieldAlert } from 'lucide-react';
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { getLiveForecast, getReplayForecast, prepareForecast, saveLiveSnapshot, getSavedPredictions, getSavedPrediction, refreshSnapshotActuals, getStatus } from './api';
import { CHART_COLORS, formatMwTick, formatUkAxisTick, formatUkDate, formatUkDateTime, tooltipBoxStyle } from './chartTheme';
import type { Intelligence, IntelligencePoint, PredictionDetails, PredictionItem, Status } from './types';

type Mode = 'replay' | 'live';
const fmt = (n: number | null | undefined, d = 0) => n == null ? '—' : n.toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d });
function isoUK(d: Date): string { const parts = new Intl.DateTimeFormat('en-GB', { year:'numeric', month:'2-digit', day:'2-digit', timeZone:'Europe/London' }).formatToParts(d); const get = (part:string) => parts.find(p=>p.type===part)?.value || '00'; return `${get('year')}-${get('month')}-${get('day')}`; }
function yesterday(): string { const d = new Date(`${isoUK(new Date())}T12:00:00Z`); d.setUTCDate(d.getUTCDate()-1); return d.toISOString().slice(0,10); }
function labelTime(v:string) { return formatUkDateTime(v); }
const pointEstimate = (p: IntelligencePoint & {prediction_mw?:number}) => p.prediction_mw ?? p.adjusted_forecast_mw ?? p.raw_forecast_mw;
const pointRows = (rows: IntelligencePoint[]) => rows.map(p => ({
  tick: formatUkAxisTick(p.start_time),
  fullTime: formatUkDateTime(p.start_time),
  raw:p.raw_forecast_mw,
  estimate:pointEstimate(p),
  actual:p.actual_mw,
  lower:p.p10_actual_mw,
  upper:p.p90_actual_mw,
  risk:p.risk_tier,
  buffer:p.downside_buffer_mw,
  start:p.start_time,
}));
function meanAbs(rows: IntelligencePoint[], field:'raw'|'estimate'): number|null {
  const values = rows.filter(p=>p.actual_mw!=null).map(p=>Math.abs((p.actual_mw as number) - (field==='raw'?p.raw_forecast_mw:pointEstimate(p))));
  return values.length ? values.reduce((a,b)=>a+b,0)/values.length : null;
}
function Pill({ risk }: {risk:string}) { return <span className={`ws-risk ws-risk-${risk}`}>{risk==='elevated'?'Elevated':risk==='watch'?'Watch':risk==='lower'?'Lower':'Not calibrated'}</span>; }
function Card({label,number,unit,sub}:{label:string;number:string;unit?:string;sub:string}) {return <div className="ws-card"><span>{label}</span><strong>{number}<small>{unit}</small></strong><p>{sub}</p></div>;}

function ComparisonChart({ rows, title }: {rows: IntelligencePoint[]; title:string}) {
  const data = useMemo(()=>pointRows(rows),[rows]);
  const deliveryLabel = data.length ? formatUkDate(data[0].start) : '—';
  return <section className="panel ws-chart"><div className="panel-head"><div><div className="section-kicker">INTERVAL FORECAST MONITOR</div><h2>{title}</h2><p>Original forecast, frozen engine estimate, available actuals and empirical scenarios · MW</p><div className="chart-context">Delivery date: <b>{deliveryLabel}</b> · Time zone: <b>UK local</b> · Hover for exact date &amp; time.</div></div></div>
    {data.length ? <ResponsiveContainer width="100%" height={330}><ComposedChart data={data} margin={{top:20,right:18,bottom:12,left:2}}><CartesianGrid stroke="#e8efeb" strokeDasharray="3 6" vertical={false}/><XAxis dataKey="tick" tick={{fontSize:10,fill:CHART_COLORS.axis}} interval="preserveStartEnd" minTickGap={34}/><YAxis tick={{fontSize:11,fill:CHART_COLORS.axis}} width={58} tickFormatter={formatMwTick}/><Tooltip labelFormatter={(_, payload)=>payload?.[0]?.payload?.fullTime ?? ''} contentStyle={tooltipBoxStyle} formatter={(v,name)=>[`${fmt(Number(v))} MW`,name]}/><Area type="monotone" dataKey="upper" name="Upper scenario P90" stroke={CHART_COLORS.upper} strokeWidth={1.4} fill={CHART_COLORS.scenarioFill} fillOpacity={0.12} connectNulls={false}/><Area type="monotone" dataKey="lower" name="Downside scenario P10" stroke={CHART_COLORS.lower} strokeDasharray="5 4" strokeWidth={1.4} fill={CHART_COLORS.scenarioFill} fillOpacity={0.03} connectNulls={false}/><Line type="monotone" dataKey="raw" name="Elexon baseline" stroke={CHART_COLORS.baseline} strokeWidth={2.2} dot={false}/><Line type="monotone" dataKey="estimate" name="WindSight estimate" stroke={CHART_COLORS.estimate} strokeWidth={2.9} dot={false}/><Line type="monotone" dataKey="actual" name="Actual generation" stroke={CHART_COLORS.actual} strokeWidth={2.5} dot={false} connectNulls={false}/></ComposedChart></ResponsiveContainer> : <div className="ws-empty-chart">No real Elexon forecasts imported for this delivery date. Use “Fetch required data”.</div>}
    <div className="series-key"><span><i style={{background:CHART_COLORS.baseline}}/>Elexon baseline</span><span><i style={{background:CHART_COLORS.estimate}}/>WindSight estimate</span><span><i style={{background:CHART_COLORS.actual}}/>Actual generation</span><span><i style={{background:CHART_COLORS.upper}}/>Upper scenario P90</span><span><i className="series-dashed" style={{borderColor:CHART_COLORS.lower}}/>Downside scenario P10</span></div>
    <p className="ws-footnote">The scenario lines are empirical error-percentile outcomes, not calibrated guarantees. Missing actuals are left blank, never represented as zero.</p></section>;
}

export default function ForecastWorkspace({mode}:{mode:Mode}) {
  const [date,setDate] = useState('2026-01-15');
  const [decisionTime,setDecisionTime] = useState('09:50');
  const [report,setReport] = useState<(Intelligence & {gate_closed?:boolean; trading_note?:string})|null>(null);
  const [saved,setSaved] = useState<PredictionItem[]>([]);
  const [selected,setSelected] = useState<PredictionDetails|null>(null);
  const [busy,setBusy] = useState(false);
  const [recalculating,setRecalculating] = useState(false);
  const requestId=useRef(0);
  const [message,setMessage] = useState('');
  const [err,setErr] = useState('');
  const [status,setStatus] = useState<Status|null>(null);

  const refresh = useCallback(async () => {
    const request = ++requestId.current;
    setErr('');
    try {
      const [result,history,state] = await Promise.all([
        mode==='replay' ? getReplayForecast(date,decisionTime) : getLiveForecast(),
        getSavedPredictions(),getStatus(),
      ]);
      if (request!==requestId.current) return false;
      setReport(result);setSaved(history.items);setStatus(state);
      if (selected) { const refreshed = await getSavedPrediction(selected.id); setSelected(refreshed); }
      return true;
    } catch(e) { if(request===requestId.current){setReport(null);setErr(e instanceof Error ? e.message : 'Unable to reach the prediction API');} return false; }
  },[date,decisionTime,mode,selected?.id]);
  useEffect(()=>{setSelected(null);setReport(null);void refresh();},[mode,date,decisionTime]);
  useEffect(()=>{if(mode!=='live')return;void prepare();const id=window.setInterval(()=>void prepare(),30*60*1000);return()=>window.clearInterval(id);},[mode]);
  useEffect(()=>{
    if (!status?.syncing) return;
    const id=window.setInterval(()=>{
      void getStatus().then(s=>{
        setStatus(s);
        if (!s.syncing) {
          setMessage(s.errors.length?`${s.errors.length} Elexon requests failed. Review errors and retry.`:'Data import complete. Recalculating with new snapshots.');
          void refresh();
        }
      }).catch(()=>{});
    },2200);
    return()=>clearInterval(id);
  },[status?.syncing,refresh]);

  async function manualRecalculate() {
    if (recalculating) return;
    setRecalculating(true);setErr('');setMessage('Recalculating from locally available Elexon snapshots…');
    try {
      const success=await refresh();
      if (success) setMessage('Calculation refreshed. Forecasts only change when Elexon source data or selected cutoff changes; use Fetch required data to update snapshots.');
      else setMessage('');
    } catch(e) { setErr(e instanceof Error?e.message:'Calculation failed'); }
    finally {setRecalculating(false);}
  }
  async function prepare() {
    setBusy(true);setErr('');setMessage('');try {
      const target=mode==='replay'?date:isoUK(new Date());
      const value=await prepareForecast(target);
      setStatus(value);
      setMessage(value.started?`Fetching source and calibration history around ${target}. This is a rolling, real-data import.`:'An import is already running.');
    } catch(e){setErr(e instanceof Error?e.message:'Could not start data import');}finally{setBusy(false);}
  }
  async function save() {
    setBusy(true);setErr('');try {
      const result=await saveLiveSnapshot(report!.cutoff_time);const refreshed=await getSavedPrediction(result.id);
      setSelected(refreshed);setSaved((await getSavedPredictions()).items);setMessage(`Issued forecast ${result.id.slice(0,8)} saved without overwriting an earlier snapshot.`);
    }catch(e){setErr(e instanceof Error?e.message:'Could not save prediction');}finally{setBusy(false);}
  }
  async function open(id:string){setBusy(true);setErr('');try{setSelected(await getSavedPrediction(id));}catch(e){setErr(e instanceof Error?e.message:'Could not read saved prediction');}finally{setBusy(false);}}
  async function refreshActuals(){if(!selected)return;setBusy(true);setErr('');try {const s=await refreshSnapshotActuals(selected.id);setStatus(s);setMessage(s.started?'Fetching current observed wind generation for the saved delivery date.':'Data sync already running.');}catch(e){setErr(e instanceof Error?e.message:'Could not refresh actuals');}finally{setBusy(false);}}
  const displayRows = selected && mode==='live' ? selected.profile : report?.profile ?? [];
  const forecast = displayRows.length ? displayRows.reduce((a,p)=>a+p.raw_forecast_mw,0)/displayRows.length : null;
  const estimate = displayRows.length ? displayRows.reduce((a,p)=>a+pointEstimate(p),0)/displayRows.length : null;
  const elevated = displayRows.filter(p=>p.risk_tier==='elevated').length;
  const planningReserve = displayRows.some(p=>p.p10_actual_mw!=null) ? displayRows.reduce((sum,p)=>sum+(p.p10_actual_mw==null?0:Math.max(pointEstimate(p)-p.p10_actual_mw,0)*p.interval_minutes/60),0) : null;
  const belowPlan = displayRows.filter(p=>p.actual_mw!=null && p.actual_mw < pointEstimate(p)).length;
  const riskRows = [...displayRows].filter(p=>p.downside_buffer_mw!=null).sort((a,b)=>(b.downside_buffer_mw??0)-(a.downside_buffer_mw??0));
  const matched = displayRows.filter(p=>p.actual_mw!=null).length;
  const chosenDay=mode==='replay'?date:isoUK(new Date());
  const delivered=new Date(`${chosenDay}T12:00:00Z`); delivered.setUTCDate(delivered.getUTCDate()+1);
  const deliveryDate=report?.delivery_date??delivered.toISOString().slice(0,10);
  const isLoaded=report!=null && report.profile.length>0;

  return <div className="ws-workspace">
    <div className="ws-hero"><div><div className="ws-hero-tag"><span/> {mode==='replay'?'AS-OF HISTORICAL REPLAY':'LIVE NEXT-DAY OUTLOOK'}</div><h2>{mode==='replay'?'Rewind a decision. See what the engine knew.':'Tomorrow’s wind. Today’s decision.'}</h2><p>{mode==='replay'?'Select a previous UK decision date. Predictions use only forecast publications available at its cutoff; actual generation is revealed afterwards for scoring.':'Issue an immutable forecast using currently published Elexon revisions and earlier observed history. Check the outcome once settlement actuals are available.'}</p></div><div className="ws-hero-icon">{mode==='replay'?<CalendarDays size={34}/>:<ShieldAlert size={34}/>}</div></div>
    <section className="panel ws-controls"><div className="ws-control-head"><div><strong>{mode==='replay'?'Historical decision date':'Current decision context'}</strong><p>{mode==='replay'?'Reconstruct any past date supported by Elexon source history':'Using the present UK date and clock; never future publications'}</p></div>{status?.syncing && <span className="ws-sync-label"><RefreshCw size={13} className="spin"/> Importing {status.sync_done}/{status.sync_total}</span>}</div><div className="ws-controls-grid">
      <label>Decision date{mode==='replay'?<input type="date" value={date} min="2020-01-01" max={yesterday()} onChange={e=>setDate(e.target.value)}/>:<div className="ws-fixed">{chosenDay} · UK</div>}</label>
      <label>Decision cutoff{mode==='replay'?<select value={decisionTime} onChange={e=>setDecisionTime(e.target.value)}><option value="08:30">08:30 UK</option><option value="09:20">09:20 UK</option><option value="09:50">09:50 UK · gate</option><option value="10:50">10:50 UK</option><option value="12:00">12:00 UK</option><option value="16:00">16:00 UK</option></select>:<div className="ws-fixed">Latest as of now</div>}</label>
      <label>Target delivery<div className="ws-fixed">{deliveryDate}</div></label>
      <button className="ws-outline" disabled={busy||!!status?.syncing} onClick={()=>void prepare()}><Database size={16}/> Fetch required data</button>
      <button className="ws-dark" disabled={busy||recalculating||!!status?.syncing} onClick={()=>void manualRecalculate()}><RefreshCw size={16} className={recalculating?'spin':''}/> {recalculating?'Calculating…':'Recalculate'}</button>
      {mode==='live' && <button className="ws-green" disabled={busy||!isLoaded} onClick={()=>void save()}><CheckCircle2 size={16}/> Issue & save forecast</button>}
    </div>{status?.syncing && <div className="ws-progress"><div style={{width:`${(status.sync_done/Math.max(1,status.sync_total))*100}%`}}/></div>}{message && <div className="ws-feedback">{message}</div>}{err && <div className="ws-feedback ws-error"><AlertCircle size={16}/>{err}</div>}{status && !status.syncing && status.errors.length>0 && <div className="ws-feedback ws-error">{status.errors.length} download errors. First: {status.errors[0]}</div>}{mode==='live' && report?.gate_closed && <div className="ws-gate"><Clock3 size={15}/> The 09:50 UK day-ahead gate has closed. Any forecasts published afterwards are monitoring information, not pre-gate purchasing forecasts.</div>}</section>
    <div className="ws-card-grid"><Card label="Original forecast · avg" number={fmt(forecast)} unit="MW" sub="Elexon's eligible delivery forecasts"/><Card label="Engine estimate · avg" number={fmt(estimate)} unit="MW" sub={report?.backtest.adjustment_enabled?'Bias correction passed prior backtest':'Unadjusted baseline retained until validation'}/><Card label="Planning reserve scenario" number={fmt(planningReserve)} unit="MWh" sub={`${elevated} elevated risk intervals · not a purchase order`}/><Card label="Observed accuracy" number={fmt(meanAbs(displayRows,'estimate'))} unit="MW MAE" sub={`${matched} observed / ${displayRows.length} predicted intervals`}/></div>
    <div className="ws-feedback">Observed shortfall in <b>{belowPlan}</b> interval(s). Planning reserve is estimated before the outcome, even if actual wind later exceeds prediction.</div><ComparisonChart rows={displayRows} title={mode==='replay'?'Historical next-day forecast versus observed generation':'Issued outlook versus observed generation'}/>
    <div className="ws-two-columns"><section className="panel ws-panel"><div className="section-kicker">PRE-DELIVERY WARNING</div><h2>Potential wind shortfall periods</h2><p>Planning reserve = engine estimate minus historical P10 scenario (floored at zero). This is *not* the quantity of power the utility must purchase.</p>{riskRows.length?riskRows.slice(0,6).map(p=><div key={p.start_time} className="ws-interval"><span>{labelTime(p.start_time)}</span><Pill risk={p.risk_tier}/><strong>{fmt(p.downside_buffer_mw)} MW</strong></div>):<p className="ws-subtle">Import sufficient earlier observations to estimate historical error scenarios.</p>}<div className="ws-caution"><ShieldAlert size={16}/> For elevated periods, review reserve/backup arrangements before the relevant decision deadline.</div></section>
    <section className="panel ws-panel"><div className="section-kicker">VALIDATED INTELLIGENCE</div><h2>How reliable is the adjustment?</h2><div className="ws-measure"><span>Historical training intervals</span><b>{fmt(report?.training.sample_intervals)}</b></div><div className="ws-measure"><span>Walk-forward test intervals</span><b>{fmt(report?.backtest.tested_intervals)}</b></div><div className="ws-measure"><span>Baseline backtest MAE</span><b>{fmt(report?.backtest.baseline_mae_mw)} MW</b></div><div className="ws-measure"><span>Candidate backtest MAE</span><b>{fmt(report?.backtest.candidate_mae_mw)} MW</b></div><div className="ws-measure"><span>Use corrected predictions?</span><b>{report?.backtest.adjustment_enabled?'Yes · validated':'No · retain baseline'}</b></div><p className="ws-subtle">Earlier deliveries train and test the model. Target-day actual generation is reserved for comparison only. Historical actual revisions lacking publication timestamps may prevent perfect reconstruction.</p></section></div>
    {mode==='live' && <section className="panel ws-panel"><div className="section-kicker">FORECAST SNAPSHOT HISTORY</div><h2>Saved predictions & actual comparisons</h2><p>A saved prediction keeps its original numbers when Elexon later publishes revisions. New actual readings only update the comparison.</p>{saved.length?<div className="ws-snap-grid">{saved.map(item=><button key={item.id} onClick={()=>void open(item.id)} className={`ws-snapshot ${selected?.id===item.id?'selected':''}`}><strong>{item.delivery_date}</strong><span>{labelTime(item.created_at)} · {item.interval_count} forecasts</span><small>View saved prediction <ArrowRight size={12}/></small></button>)}</div>:<p className="ws-subtle">No issued predictions yet. Import forecasts then press “Issue & save forecast”.</p>}{selected && <div className="ws-snapshot-detail"><div className="ws-detail-head"><div><strong>Issued forecast · {selected.id.slice(0,8)}</strong><p>{selected.comparison.state==='awaiting_actuals'?'Actual generation not available yet':`${selected.comparison.matched_intervals}/${selected.comparison.forecast_intervals} intervals have actual generation`}</p></div><button className="ws-outline" disabled={busy||!!status?.syncing} onClick={()=>void refreshActuals()}><RefreshCw size={15}/> Update actuals</button></div><div className="ws-metrics-line"><span>Elexon MAE <b>{fmt(selected.comparison.baseline.mae_mw)} MW</b></span><span>Engine MAE <b>{fmt(selected.comparison.engine.mae_mw)} MW</b></span><span>Observed <b>{selected.comparison.matched_intervals}/{selected.comparison.forecast_intervals}</b></span></div></div>}</section>}
    <section className="panel ws-panel"><div className="section-kicker">PER-INTERVAL DETAIL</div><h2>Forecast, downside & actual</h2><div className="table-scroll"><table><thead><tr><th>DELIVERY UK</th><th>BASELINE MW</th><th>ENGINE MW</th><th>P10 MW</th><th>SHORTFALL BUFFER</th><th>ACTUAL MW</th><th>ERROR MW</th><th>RESULT</th><th>RISK</th></tr></thead><tbody>{displayRows.length?displayRows.map(p=><tr key={p.start_time}><td>{labelTime(p.start_time)}</td><td>{fmt(p.raw_forecast_mw)}</td><td>{fmt(pointEstimate(p))}</td><td>{fmt(p.p10_actual_mw)}</td><td>{fmt(p.downside_buffer_mw)}</td><td>{fmt(p.actual_mw)}</td><td><b className={p.actual_mw==null?'':p.actual_mw<pointEstimate(p)?'h-bad-number':'h-good-number'}>{p.actual_mw==null?'—':`${p.actual_mw>pointEstimate(p)?'+':''}${fmt(p.actual_mw-pointEstimate(p))}`}</b></td><td>{p.actual_mw==null?<span className="h-signal h-pending">Awaiting actual</span>:p.actual_mw<pointEstimate(p)?<span className="h-signal h-shortfall">Below plan</span>:<span className="h-signal h-surplus">Met/exceeded</span>}</td><td><Pill risk={p.risk_tier}/></td></tr>):<tr><td colSpan={9} className="empty-cell">No observed Elexon data is being fabricated. Fetch required data to populate this table.</td></tr>}</tbody></table></div></section>
    <p className="ws-disclaimer"><Eye size={15}/> Decision support only. Wind forecast shortfall ≠ total grid supply shortfall. No demand, price, capacity commitments or balancing market data are used. P10/P90 scenarios are empirically estimated rather than guaranteed confidence bounds.</p>
  </div>;
}
