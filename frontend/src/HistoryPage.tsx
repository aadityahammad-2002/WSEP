import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CalendarRange, ChevronDown, ChevronLeft, ChevronRight, Database, Download, RefreshCw, ShieldCheck } from 'lucide-react';
import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { getHistory, getStatus, importHistory } from './api';
import { CHART_COLORS, formatMwTick, formatUkAxisTick, formatUkDateTime, tooltipBoxStyle } from './chartTheme';
import type { HistoryDay, HistoryInterval, HistoryResult, Status } from './types';

const fmt = (n:number|null|undefined, places=0) => n == null ? '—' : n.toLocaleString('en-GB',{maximumFractionDigits:places,minimumFractionDigits:places});
const formatWhen = (s:string) => formatUkDateTime(s);
const dateForInput = (offset:number) => {const d=new Date();const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(d);const get=(name:string)=>parts.find(x=>x.type===name)?.value??'01';const utc=new Date(`${get('year')}-${get('month')}-${get('day')}T12:00:00Z`);utc.setUTCDate(utc.getUTCDate()+offset);return utc.toISOString().slice(0,10);};
const errorState = (value:number|null) => value===null ? 'pending' : value<0?'shortfall':'surplus';
function Signal({value}:{value:number|null}) {const kind=errorState(value);return <span className={`h-signal h-${kind}`}>{kind==='shortfall'?'● Wind below plan':kind==='surplus'?'● Met / exceeded':'○ Awaiting actual'}</span>;}
function CsvButton({items}:{items:HistoryDay[]}) {
  function download(){
    const lines=[['decision_date','delivery_date','delivery_start_utc','published_utc','baseline_mw','engine_prediction_mw','actual_mw','signed_error_mw','result','planning_buffer_mw','planning_buffer_mwh','observed_shortfall_mwh','risk_tier']];
    for(const day of items) for(const row of day.intervals) lines.push([day.decision_date,day.delivery_date,row.start_time,row.publish_time,row.baseline_mw,row.predicted_mw,row.actual_mw,row.error_mw,row.result,row.planning_buffer_mw,row.planning_buffer_mwh,row.observed_shortfall_mwh,row.risk_tier].map(x=>String(x??'')));
    const body=lines.map(row=>row.map(cell=>'"'+cell.replaceAll('"','""')+'"').join(',')).join('\r\n');
    const url=URL.createObjectURL(new Blob([body],{type:'text/csv;charset=utf-8'}));
    const anchor=document.createElement('a');anchor.href=url;anchor.download='windsight-history-visible-page.csv';anchor.click();URL.revokeObjectURL(url);
  }
  return <button className="h-outline" disabled={!items.some(x=>x.intervals.length)} onClick={download}><Download size={15}/> Export visible page CSV</button>;
}
function DailyReport({day}:{day:HistoryDay}) {
  const [open,setOpen]=useState(false);
  const data=useMemo(()=>day.intervals.map((p:HistoryInterval)=>({tick:formatUkAxisTick(p.start_time),fullTime:formatWhen(p.start_time),forecast:p.baseline_mw,prediction:p.predicted_mw,actual:p.actual_mw,downside:p.planning_buffer_mw})),[day]);
  return <article className="h-day">
    <button className="h-day-head" onClick={()=>setOpen(v=>!v)} aria-expanded={open}>
      <div><strong>{day.delivery_date}</strong><small>Delivery · decision {day.decision_date} · {day.forecast_intervals} intervals</small></div>
      <div className="h-day-head-stats"><span>Engine avg <b>{fmt(day.mean_prediction_mw)} MW</b></span><span>Actual avg <b>{fmt(day.mean_actual_mw)} MW</b></span><span>MAE <b>{fmt(day.mae_mw)} MW</b></span><span>Reserve scenario <b>{fmt(day.planned_buffer_mwh)} MWh</b></span></div>
      <ChevronDown size={17} className={open?'h-rotated':''}/>
    </button>
    {open && <div className="h-detail">
      <div className="h-detail-metrics"><span><b className="h-bad-number">{day.shortfall_intervals}</b> below prediction</span><span><b className="h-good-number">{day.surplus_intervals}</b> met/exceeded</span><span><b>{fmt(day.observed_shortfall_mwh)}</b> observed wind shortfall MWh</span><span><b>{day.scored_intervals}/{day.forecast_intervals}</b> actual intervals</span></div>
      {data.length ? <><div className="chart-context">Delivery day chart · Time zone: <b>UK local</b> · Hover any point for exact date &amp; time.</div><div className="h-chart"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={data} margin={{top:10,right:5,left:-8,bottom:8}}><CartesianGrid vertical={false} stroke="#e7eee9" strokeDasharray="4 5"/><XAxis dataKey="tick" tick={{fontSize:10,fill:CHART_COLORS.axis}} minTickGap={38}/><YAxis width={65} tick={{fontSize:10,fill:CHART_COLORS.axis}} tickFormatter={formatMwTick}/><Tooltip labelFormatter={(_, payload)=>payload?.[0]?.payload?.fullTime ?? ''} contentStyle={tooltipBoxStyle} formatter={(value,name)=>[`${fmt(typeof value==='number'?value:null)} MW`,String(name)]}/><Line type="monotone" dataKey="forecast" name="Elexon forecast" stroke={CHART_COLORS.baseline} dot={false} strokeWidth={2.2}/><Line type="monotone" dataKey="prediction" name="Engine prediction" stroke={CHART_COLORS.estimate} dot={false} strokeWidth={2.8}/><Line type="monotone" dataKey="actual" name="Actual generation" stroke={CHART_COLORS.actual} dot={false} strokeWidth={2.4}/></ComposedChart></ResponsiveContainer></div><div className="series-key"><span><i style={{background:CHART_COLORS.baseline}}/>Elexon forecast</span><span><i style={{background:CHART_COLORS.estimate}}/>Engine prediction</span><span><i style={{background:CHART_COLORS.actual}}/>Actual generation</span></div></> : <div className="h-empty">No source forecasts available yet. Fetch this period to calculate a replay.</div>}
      <div className="table-scroll"><table><thead><tr><th>DELIVERY (UK)</th><th>ELEXON MW</th><th>ENGINE MW</th><th>ACTUAL MW</th><th>ERROR (ACTUAL − ENGINE)</th><th>RESULT</th><th>PLANNING RESERVE MW</th><th>OBSERVED SHORTFALL MWh</th></tr></thead><tbody>{day.intervals.length?day.intervals.map(p=><tr key={p.start_time}><td>{formatWhen(p.start_time)}</td><td>{fmt(p.baseline_mw)}</td><td><b>{fmt(p.predicted_mw)}</b></td><td>{fmt(p.actual_mw)}</td><td><strong className={p.error_mw==null?'':p.error_mw<0?'h-bad-number':'h-good-number'}>{p.error_mw==null?'—':`${p.error_mw>0?'+':''}${fmt(p.error_mw)} MW`}</strong></td><td><Signal value={p.error_mw}/></td><td><b>{fmt(p.planning_buffer_mw)} MW</b></td><td>{fmt(p.observed_shortfall_mwh)}</td></tr>):<tr><td colSpan={8} className="empty-cell">No forecasts loaded for this day.</td></tr>}</tbody></table></div>
      {!!day.missing.length && <p className="h-muted">Missing source partitions: {day.missing.join(', ')}</p>}
      <p className="h-muted">A positive error means actual wind exceeded the engine estimate. Planning reserve is calculated from pre-decision downside scenarios, not from the actual result.</p>
    </div>}
  </article>;
}
export default function HistoryPage(){
  const [draftStart,setDraftStart]=useState(dateForInput(-7));
  const [draftEnd,setDraftEnd]=useState(dateForInput(-1));
  const [range,setRange]=useState(()=>({start:dateForInput(-7),end:dateForInput(-1)}));
  const [time,setTime]=useState('09:50');
  const [page,setPage]=useState(1);
  const [report,setReport]=useState<HistoryResult|null>(null);
  const [status,setStatus]=useState<Status|null>(null);
  const [loading,setLoading]=useState(false);
  const [importing,setImporting]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const generation=useRef(0);
  const load=useCallback(async()=>{
    const request=++generation.current;setLoading(true);setError('');
    try {const [result,st]=await Promise.all([getHistory(range.start,range.end,page,time),getStatus()]);if(request!==generation.current)return;setReport(result);setStatus(st);}
    catch(e){if(request===generation.current){setReport(null);setError(e instanceof Error?e.message:'History request failed');}}
    finally{if(request===generation.current)setLoading(false);}
  },[range,page,time]);
  useEffect(()=>{void load();},[load]);
  useEffect(()=>{if(!status?.syncing)return;const interval=window.setInterval(async()=>{try{const st=await getStatus();setStatus(st);if(!st.syncing){setImporting(false);setNotice(st.errors.length?`${st.errors.length} Elexon downloads failed; inspect the status and retry.`:'Download completed. Refreshing this history page.');void load();}}catch{/* Show API errors via the explicit refresh. */}},2500);return()=>clearInterval(interval);},[status?.syncing,load]);
  function apply(){if(draftStart>draftEnd){setError('Start date must not be after end date.');return;}if(draftEnd>dateForInput(0)){setError('Future decision dates are not historical records.');return;}const span=(new Date(draftEnd).getTime()-new Date(draftStart).getTime())/86400000;if(span>365){setError('Select up to 366 days; use adjacent ranges for longer history.');return;}setError('');setNotice('');setPage(1);setRange({start:draftStart,end:draftEnd});}
  async function importPage(){const rows=report?.days??[];if(!rows.length)return;const from=rows[rows.length-1].decision_date;const to=rows[0].decision_date;setImporting(true);setError('');try{const st=await importHistory(from,to);setStatus(st);setNotice(st.started?`Fetching ${from} to ${to} and prior calibration history.`:'Another import is already active.');if(!st.started)setImporting(false);}catch(e){setError(e instanceof Error?e.message:'Could not fetch data');setImporting(false);}}
  const days=report?.days??[];
  const totals=useMemo(()=>({intervals:days.reduce((x,d)=>x+d.forecast_intervals,0),scored:days.reduce((x,d)=>x+d.scored_intervals,0),reserve:days.reduce((x,d)=>x+(d.planned_buffer_mwh??0),0),actualShortfall:days.reduce((x,d)=>x+(d.observed_shortfall_mwh??0),0),red:days.reduce((x,d)=>x+d.shortfall_intervals,0),green:days.reduce((x,d)=>x+d.surplus_intervals,0)}),[days]);
  return <div className="h-page">
    <section className="h-banner"><div><div className="section-kicker">HISTORICAL AUDIT & REPLAY</div><h2>Explore any previous decision period.</h2><p>See what the engine could predict then, what actually happened, how far the forecast missed, and the advance wind contingency estimated before delivery.</p></div><CalendarRange size={43}/></section>
    <section className="panel h-filters"><label>From (decision date)<input aria-label="History start date" type="date" min="2020-01-01" max={dateForInput(0)} value={draftStart} onChange={e=>setDraftStart(e.target.value)}/></label><label>To (decision date)<input aria-label="History end date" type="date" min="2020-01-01" max={dateForInput(0)} value={draftEnd} onChange={e=>setDraftEnd(e.target.value)}/></label><label>UK decision cutoff<select value={time} onChange={e=>{setTime(e.target.value);setPage(1);}}><option value="08:30">08:30 UK</option><option value="09:50">09:50 UK · gate</option><option value="12:00">12:00 UK</option><option value="16:00">16:00 UK</option></select></label><button className="h-primary" onClick={apply}><CalendarRange size={16}/> Apply range</button><button className="h-outline" disabled={loading} onClick={()=>void load()}><RefreshCw size={16} className={loading?'spin':''}/> Refresh</button></section>
    {(error||notice)&&<div className={`h-message ${error?'h-message-bad':''}`} role="status">{error||notice}</div>}
    {status?.syncing&&<div className="h-message"><RefreshCw size={16} className="spin"/> Importing Elexon {status.sync_done}/{status.sync_total} source requests</div>}
    <div className="h-stats"><div><small>Predicted intervals (visible)</small><strong>{fmt(totals.intervals)}</strong></div><div><small>Scored intervals</small><strong>{fmt(totals.scored)}</strong></div><div><small>Met/exceeded</small><strong className="h-good-number">{fmt(totals.green)}</strong></div><div><small>Below prediction</small><strong className="h-bad-number">{fmt(totals.red)}</strong></div><div><small>Advance planning scenario</small><strong>{days.some(x=>x.planned_buffer_mwh!=null)?fmt(totals.reserve):'—'} <em>MWh</em></strong></div><div><small>Observed wind shortfall</small><strong>{totals.scored?fmt(totals.actualShortfall):'—'} <em>MWh</em></strong></div></div>
    <section className="panel h-results"><div className="h-results-heading"><div><div className="section-kicker">DATE RANGE RESULTS</div><h2>{range.start} → {range.end}</h2><p>{report?`${report.total_days} decision days · page ${report.page} of ${report.total_pages}`:'Loading selected dates'} · Click a day to inspect its chart and each interval.</p></div><div className="h-actions"><button className="h-outline" onClick={()=>void importPage()} disabled={importing||!!status?.syncing||!days.length}><Database size={15}/> Fetch visible dates</button><CsvButton items={days}/></div></div>
    {loading?<div className="h-empty"><RefreshCw size={20} className="spin"/> Loading historical predictions…</div>:days.length?days.map(d=><DailyReport key={`${d.decision_date}-${time}`} day={d}/>):<div className="h-empty">No dates on this page. Choose a valid range or go to the previous page.</div>}
    <div className="h-pagination"><button onClick={()=>setPage(p=>Math.max(p-1,1))} disabled={page<=1||loading}><ChevronLeft size={16}/> Newer</button><span>Page {report?.page??page} / {report?.total_pages??'—'}</span><button onClick={()=>setPage(p=>p+1)} disabled={loading||page>=(report?.total_pages??1)}>Older <ChevronRight size={16}/></button></div></section>
    <div className="h-explanation"><ShieldCheck size={19}/><div><b>How to read the colours</b><p><span className="h-good-number">Green</span> = actual wind met or exceeded the original decision-time *engine* estimate. <span className="h-bad-number">Red</span> = actual wind fell below it. An advance planning buffer is still shown for green outcomes because it was based on uncertainty known before delivery, not hindsight.</p><p><AlertTriangle size={14}/> The buffer describes wind-side contingency exposure; it is <b>not</b> a mandatory additional purchase. Demand, contracted generation, reserve commitments and prices are outside the available dataset.</p></div></div>
  </div>;
}
