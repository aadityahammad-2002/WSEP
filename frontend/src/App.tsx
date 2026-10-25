import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, ArrowRight, BarChart3, Check, ChevronDown,
  CircleAlert, Clock3, Database, Download, FileText, Gauge, GitCompareArrows, BrainCircuit,
  Info, Layers3, LoaderCircle, Menu, RefreshCw, ShieldCheck, TrendingDown, Waves, Wind, X
} from 'lucide-react';
import {
  Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip,
  XAxis, YAxis, Bar, BarChart, Cell
} from 'recharts';
import ForecastWorkspace from './ForecastWorkspace';
import HistoryPage from './HistoryPage';
import { clearDataCache, exportUrl, getComparison, getIntelligence, getMonthly, getRevisions, getStatus, prepareForecast } from './api';
import { CHART_COLORS, formatMwTick, formatUkAxisTick, formatUkDateTime, formatUkTime, getDailyErrorColor, tooltipBoxStyle } from './chartTheme';
import type { Comparison, ForecastProfilePoint, Intelligence, IntelligencePoint, Monthly, Revision, Status } from './types';

const TIME_OPTIONS = ['08:30', '09:20', '09:50', '10:50', '12:00', '16:00'];
const fmt = (number: number | null | undefined, digits = 0) => number == null ? '—' : number.toLocaleString('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const timeStamp = (value: string) => formatUkDateTime(value);
const timeOfDay = (value: string) => formatUkTime(value);
const signed = (value: number | null | undefined) => value == null ? '—' : `${value > 0 ? '+' : ''}${fmt(value)}`;
const ukYesterday = () => {const parts=new Intl.DateTimeFormat('en-GB',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:'Europe/London'}).formatToParts(new Date());const get=(part:string)=>parts.find(x=>x.type===part)?.value??'01';const day=new Date(`${get('year')}-${get('month')}-${get('day')}T12:00:00Z`);day.setUTCDate(day.getUTCDate()-1);return day.toISOString().slice(0,10);};

type Tab = 'replay' | 'live' | 'history' | 'overview' | 'intelligence' | 'records' | 'methodology';

function MiniBrand() {
  return <div className="brand"><div className="brand-mark"><Waves size={23} strokeWidth={2.3}/></div><div><strong>WindSight</strong><small>ENERGY INTELLIGENCE</small></div></div>;
}

function Sidebar({ tab, setTab, open, setOpen, apiReady }: { tab: Tab; setTab: (tab: Tab) => void; open: boolean; setOpen: (value: boolean) => void; apiReady: boolean }) {
  const menu: { key: Tab; label: string; icon: typeof Activity }[] = [
    { key:'replay', label:'Historical replay', icon:GitCompareArrows },
    { key:'live', label:'Live prediction', icon:Wind },
    { key:'history', label:'History · date range', icon:Clock3 },
    { key:'overview', label:'Forecast analytics', icon:BarChart3 },
    { key:'intelligence', label:'Decision intelligence', icon:BrainCircuit },
    { key:'records', label:'Settlement records', icon:Layers3 },
    { key:'methodology', label:'Methodology', icon:FileText },
  ];
  return <>
    {open && <div className="sidebar-scrim" onClick={() => setOpen(false)} />}
    <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
      <div className="sidebar-top"><MiniBrand/><button className="close-mobile icon-button" onClick={() => setOpen(false)} aria-label="Close navigation"><X size={20}/></button></div>
      <div className="nav-title">WORKSPACE</div>
      <nav aria-label="Main navigation">{menu.map(({ key, label, icon: Icon }) => <button key={key} className={`nav-item ${tab === key ? 'active' : ''}`} onClick={() => { setTab(key); setOpen(false); }}><Icon size={18}/><span>{label}</span>{tab === key && <span className="nav-pip"/>}</button>)}</nav>
      <div className="nav-title nav-title-lower">DATA SOURCE</div>
      <div className="source-nav"><div className="source-icon"><Database size={18}/></div><div><strong>BMRS / Elexon</strong><span>{apiReady?'Local API responding':'Check backend connection'}</span></div><span className={`source-dot ${apiReady?'':'source-dot-offline'}`}/></div>
      <div className="sidebar-spacer"/>
      <div className="sidebar-note"><div className="note-icon"><ShieldCheck size={18}/></div><strong>Built for better decisions</strong><p>Forecasts are reconstructed as they were known before gate closure.</p></div>
      <div className="sidebar-footer"><span className="avatar">WS</span><div><strong>UK Power Desk</strong><small>Decision intelligence</small></div><ChevronDown size={15}/></div>
    </aside>
  </>;
}

function Kpi({ icon: Icon, label, value, unit, note, tone = 'green' }: { icon: typeof Activity; label: string; value: string; unit?: string; note: string; tone?: 'green' | 'orange' | 'blue' | 'purple' }) {
  return <div className="kpi"><div className="kpi-head"><span>{label}</span><span className={`kpi-icon ${tone}`}><Icon size={18}/></span></div><div className="kpi-value">{value}{unit && <span>{unit}</span>}</div><div className="kpi-note">{note}</div></div>;
}

function VizTip({ active, payload }: { active?: boolean; payload?: { payload: { time: string; forecast: number; engine: number; actual: number | null; error: number | null; publish: string } }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return <div className="viz-tip"><strong>{p.time}</strong><div><span className="tip-dot forecast"/>Forecast <b>{fmt(p.forecast)} MW</b></div><div><span className="tip-dot engine"/>Engine estimate <b>{fmt(p.engine)} MW</b></div><div><span className="tip-dot actual"/>Actual <b>{fmt(p.actual)} MW</b></div><div className="tip-sep">Error <b className={p.error != null && p.error < 0 ? 'danger-text' : 'positive-text'}>{signed(p.error)} MW</b></div><small>Issued: {p.publish} · UK local</small></div>;
}

function PowerChart({ points, intelligence, loading, matched }: { points: ForecastProfilePoint[]; intelligence: Intelligence | null; loading: boolean; matched: number }) {
  const chart = useMemo(() => points.map(p => ({
    time: formatUkDateTime(p.start_time),
    tick: formatUkAxisTick(p.start_time),
    forecast: p.forecast_mw,
    actual: p.actual_mw,
    engine: intelligence?.profile.find(x=>x.start_time===p.start_time)?.adjusted_forecast_mw ?? p.forecast_mw,
    error: p.error_mw,
    publish: formatUkDateTime(p.publish_time)
  })), [points,intelligence]);
  return <div className="panel chart-panel">
    <div className="panel-head"><div><div className="section-kicker">DELIVERY PROFILE</div><h2>Forecast vs. actual generation</h2><p>Power by delivery interval · MW</p><div className="chart-context">Time zone: <b>UK local</b> · Hover a point to inspect exact date &amp; time.</div></div><div className="legend-inline"><span><i className="legend-dot forecast"/>Forecast</span><span><i className="legend-dot engine"/>Engine estimate</span><span><i className="legend-dot actual"/>Actual</span></div></div>
    {loading ? <div className="chart-loading"><LoaderCircle className="spin" size={26}/>Loading records</div> : points.length === 0 ? <EmptyChart/> :
    <div className="power-chart"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={chart} margin={{ top: 12, right: 12, left: -12, bottom: 0 }}>
      <defs><linearGradient id="forecastFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={CHART_COLORS.baseline} stopOpacity={0.16}/><stop offset="95%" stopColor={CHART_COLORS.baseline} stopOpacity={0}/></linearGradient></defs>
      <CartesianGrid vertical={false} stroke="#e9eeec" strokeDasharray="4 5"/>
      <XAxis dataKey="tick" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: CHART_COLORS.axis }} minTickGap={30} dy={12}/>
      <YAxis tickLine={false} axisLine={false} tickFormatter={formatMwTick} tick={{ fontSize: 11, fill: CHART_COLORS.axis }}/>
      <Tooltip content={<VizTip/>}/>
      <Area dataKey="forecast" type="monotone" stroke="none" fill="url(#forecastFill)" legendType="none" tooltipType="none"/>
      <Line dataKey="forecast" stroke={CHART_COLORS.baseline} strokeWidth={2.8} dot={false} type="monotone" name="Forecast" activeDot={{ r: 5, strokeWidth: 3, stroke: '#fff' }}/>
      <Line dataKey="engine" stroke={CHART_COLORS.estimate} strokeWidth={2.3} strokeDasharray="6 4" dot={false} type="monotone" name="Engine estimate"/>
      <Line dataKey="actual" stroke={CHART_COLORS.actual} strokeWidth={2.6} dot={false} type="monotone" name="Actual" activeDot={{ r: 5, strokeWidth: 3, stroke: '#fff' }}/>
    </ComposedChart></ResponsiveContainer></div>}
    <div className="chart-footer"><span><span className="footer-dot"/>N2EX day-ahead decision context</span><span>{matched} matched / {points.length} forecast intervals</span></div>
  </div>;
}
function EmptyChart() { return <div className="empty-chart"><div className="empty-ring"><Waves size={29}/></div><strong>No verified measurements to plot</strong><p>Load the Elexon historical snapshots to view forecast and actual generation.</p></div>; }

function ErrorChart({ monthly }: { monthly: Monthly | null }) {
  const data = (monthly?.daily ?? []).map(d => ({ day: d.decision_date.slice(5), mae: d.mae_mw, available: d.available }));
  return <div className="panel error-panel"><div className="panel-head"><div><div className="section-kicker">HISTORICAL PERFORMANCE</div><h2>Daily forecast error</h2><p>Mean absolute error · MW</p><div className="chart-context">Green = lower error, amber = moderate error, red = higher error.</div></div><span className="pill">{(monthly?.metrics.total_days ?? 0)} decisions · selected month</span></div>
    <div className="bar-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{ top: 8, right: 4, left: -20, bottom: 0 }} barCategoryGap="31%"><CartesianGrid vertical={false} stroke="#eef1f0" strokeDasharray="4 5"/><XAxis dataKey="day" tick={{ fontSize: 10, fill: CHART_COLORS.axis }} tickLine={false} axisLine={false} interval={4}/><YAxis tick={{ fontSize: 10, fill: CHART_COLORS.axis }} tickLine={false} axisLine={false} tickFormatter={formatMwTick}/><Tooltip content={({active,payload}) => active && payload?.length ? <div className="viz-tip"><strong>{payload[0]?.payload.day}</strong><div>MAE <b>{fmt(payload[0]?.payload.mae)} MW</b></div></div> : null} contentStyle={tooltipBoxStyle}/><Bar dataKey="mae" radius={[4,4,0,0]} maxBarSize={13}>{data.map((d,i) => <Cell key={i} fill={getDailyErrorColor(d.mae)}/>)}</Bar></BarChart></ResponsiveContainer></div>
    <div className="side-note"><Info size={15}/> Days without source data are not assigned artificial errors.</div>
  </div>;
}

function Exposure({ comparison }: { comparison: Comparison | null }) {
  const m = comparison?.metrics;
  const freq = m?.shortfall_frequency_pct;
  return <div className="panel exposure-panel"><div className="panel-head"><div><div className="section-kicker">DECISION RISK</div><h2>Wind shortfall exposure</h2><p>At the selected decision cutoff</p></div><span className="round-arrow"><TrendingDown size={19}/></span></div>
    <div className="exposure-main"><span>Wind shortfall frequency</span><strong>{fmt(freq,1)}<small>{freq == null ? '' : '%'}</small></strong></div><div className="progress-track"><div style={{ width: `${freq ?? 0}%` }}/></div>
    <div className="exposure-split"><div><span>P90 error</span><strong>{fmt(m?.p90_abs_error_mw)} <small>MW</small></strong></div><div><span>Shortfall exposure</span><strong>{fmt(m?.shortfall_mwh)} <small>MWh</small></strong></div></div>
    <div className="exposure-warning"><CircleAlert size={16}/> This measures wind forecast uncertainty, not actual energy procurement.</div>
  </div>;
}

function Table({ points, intelligence, date, time, onVersion }: { points: ForecastProfilePoint[]; intelligence: Intelligence | null; date: string; time: string; onVersion: (point: ForecastProfilePoint) => void }) {
  return <div className="panel table-panel"><div className="panel-head table-head"><div><div className="section-kicker">AUDIT TRAIL</div><h2>Settlement comparison</h2><p>Every eligible forecast joined to measured wind output</p></div><a href={exportUrl(date,time)} className={`outline-button ${points.length === 0 ? 'disabled-link' : ''}`} onClick={e => { if (!points.length) e.preventDefault(); }}><Download size={16}/>Export CSV</a></div>
    <div className="table-scroll"><table><thead><tr><th>DELIVERY UK</th><th>ELEXON</th><th>ENGINE</th><th>ACTUAL</th><th>ERROR (ACTUAL − ENGINE)</th><th>RESULT</th><th>PLANNING RESERVE</th><th>ISSUED UK</th><th>REVISIONS</th></tr></thead><tbody>{points.length ? points.map(p => {const intel=intelligence?.profile.find(x=>x.start_time===p.start_time);const predicted=intel?.adjusted_forecast_mw??p.forecast_mw;const error=p.actual_mw==null?null:p.actual_mw-predicted;const reserve=intel?.p10_actual_mw==null?null:Math.max(predicted-intel.p10_actual_mw,0);return <tr key={p.start_time}><td className="bold-cell">{timeStamp(p.start_time)}</td><td>{fmt(p.forecast_mw)} MW</td><td><b>{fmt(predicted)} MW</b></td><td>{fmt(p.actual_mw)} MW</td><td><span className={`error-chip ${error==null?'':error<0?'error-negative':'error-positive'}`}>{signed(error)} MW</span></td><td>{error==null?<span className="h-signal h-pending">Awaiting actual</span>:error<0?<span className="h-signal h-shortfall">Below plan</span>:<span className="h-signal h-surplus">Met/exceeded</span>}</td><td>{fmt(reserve)} MW</td><td>{timeStamp(p.publish_time)}</td><td><button className="details-button" onClick={() => onVersion(p)}>Inspect <ArrowRight size={14}/></button></td></tr>}) : <tr><td colSpan={9} className="empty-cell">No forecast intervals available for this decision date.</td></tr>}</tbody></table></div>
    <div className="table-footer">Showing {points.length} forecast intervals · Dates shown in UK local time · Error = actual − engine · Reserve is an advance wind uncertainty scenario</div>
  </div>;
}

function Methodology() {
  return <div className="method-grid"><div className="panel method-card"><span className="step-number">01</span><h2>Reconstruct the decision</h2><p>For each selected decision date, reconstruct the next delivery day's forecast using only WINDFOR publications available at the chosen UK-local cutoff. The historical analytics controls accept previously recorded decision dates.</p><div className="formula">published_at ≤ gate_closure</div></div>
  <div className="panel method-card"><span className="step-number">02</span><h2>Align measured generation</h2><p>Match generation by delivery interval in UTC. When the forecast is hourly, average the two complete FUELHH half-hour MW readings. Missing readings stay missing.</p><div className="formula">actual_hour = (MW₁ + MW₂) / 2</div></div>
  <div className="panel method-card"><span className="step-number">03</span><h2>Quantify uncertainty</h2><p>Report signed error, MAE, RMSE, bias and shortfall frequency. Negative signed error means wind generated less than forecast.</p><div className="formula">signed_error = actual − forecast</div></div>
  <div className="panel method-card"><span className="step-number">04</span><h2>Separate risk from purchase</h2><p>Wind shortfall exposure is the interval-by-interval positive difference between forecast and observed power, multiplied by interval length. This is not a recommended procurement volume.</p><div className="formula">Σ max(forecast − actual, 0) × hours</div></div>
  <div className="panel methodology-foot"><ShieldCheck size={20}/><div><strong>Traceable by design</strong><span>Raw Elexon WINDFOR and FUELHH snapshots are stored separately; each observation exposes its source publication time. No additional energy, demand or price feeds are used.</span></div></div></div>;
}

function riskName(tier: IntelligencePoint['risk_tier']) {
  return tier === 'elevated' ? 'Elevated' : tier === 'watch' ? 'Watch' : tier === 'lower' ? 'Lower' : 'No estimate';
}

function IntelligencePanel({ report, loading }: { report: Intelligence | null; loading: boolean }) {
  if (loading) return <div className="panel intelligence-empty"><LoaderCircle className="spin" size={25}/> Preparing decision evidence</div>;
  if (!report) return <div className="panel intelligence-empty"><CircleAlert size={24}/> The intelligence endpoint is unavailable. Check the backend connection.</div>;
  const summary = report.summary;
  const gate = report.backtest;
  const engineReserve = report.profile.some(p=>p.p10_actual_mw!=null) ? report.profile.reduce((sum,p)=>sum+(p.p10_actual_mw==null?0:Math.max((p.adjusted_forecast_mw??p.raw_forecast_mw)-p.p10_actual_mw,0)*p.interval_minutes/60),0) : null;
  const chart = report.profile.map(point => ({
    time: formatUkDateTime(point.start_time),
    tick: formatUkAxisTick(point.start_time),
    forecast: point.raw_forecast_mw,
    adjusted: point.adjusted_forecast_mw,
    actual: point.actual_mw,
    range: point.p10_actual_mw == null || point.p90_actual_mw == null ? null : [point.p10_actual_mw, point.p90_actual_mw],
  }));
  return <div className="intelligence-page">
    <div className="intel-intro panel">
      <div className="intel-intro-top"><div><span className="section-kicker">HISTORICAL DECISION EVIDENCE</span><h2>Advance wind contingency before purchase</h2><p>At the selected cutoff, explore plausible downside based only on previously observed Elexon errors.</p></div><span className={`intel-state ${report.status === 'ready' ? 'intel-ready' : ''}`}>{report.status === 'ready' ? 'Scenarios available' : 'Not enough history'}</span></div>
      <div className="intel-evidence"><span><b>{report.training.sample_days}</b> earlier decision days</span><span><b>{report.training.sample_intervals}</b> historical comparisons</span><span><b>{gate.tested_intervals}</b> walk-forward test intervals</span></div>
      <p className="intel-policy">History ends at least one complete calendar day before this purchase decision. Forecasts and available outturn revisions are filtered by their timestamps.</p>
    </div>
    <div className="intel-stat-grid">
      <div className="panel intel-stat"><span>Wind downside flags</span><strong>{report.status === 'ready' ? summary.elevated_risk_intervals : '—'}<small> intervals</small></strong><p>Empirical downside ≥20% of interval forecast</p></div>
      <div className="panel intel-stat"><span>Advance wind reserve scenario</span><strong>{fmt(engineReserve)}<small> MWh</small></strong><p>Engine minus P10 scenario; not a required purchase</p></div>
      <div className="panel intel-stat"><span>Walk-forward MAE improvement</span><strong>{gate.status === 'validated' ? signed(gate.candidate_mae_improvement_pct) : '—'}<small>{gate.status === 'validated' ? ' %' : ''}</small></strong><p>{gate.adjustment_enabled ? 'Bias correction enabled' : 'Original forecasts retained'}</p></div>
      <div className="panel intel-stat"><span>80% scenario-band coverage</span><strong>{gate.status === 'validated' ? fmt(gate.empirical_80pct_band_coverage_pct,1) : '—'}<small>{gate.status === 'validated' ? ' %' : ''}</small></strong><p>Observed holdout coverage, not a guarantee</p></div>
    </div>
    <div className="panel intel-chart-panel">
      <div className="panel-head"><div><div className="section-kicker">SCENARIO ENVELOPE</div><h2>Expected wind and downside range</h2><p>Raw forecast, observed output and historical P10–P90 actual scenarios · MW</p><div className="chart-context">Time zone: <b>UK local</b> · Hover a point to inspect exact date &amp; time.</div></div></div>
      {chart.length ? <div className="intel-chart"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={chart} margin={{top:10,right:10,bottom:2,left:-9}}>
        <CartesianGrid vertical={false} stroke="#e9eeec" strokeDasharray="4 5"/>
        <XAxis dataKey="tick" tickLine={false} axisLine={false} minTickGap={24} tick={{fontSize:11,fill:CHART_COLORS.axis}}/>
        <YAxis tickLine={false} axisLine={false} tick={{fontSize:11,fill:CHART_COLORS.axis}} tickFormatter={formatMwTick}/>
        <Tooltip labelFormatter={(_, payload)=>payload?.[0]?.payload?.time ?? ''} contentStyle={tooltipBoxStyle} formatter={(value: unknown, name: unknown) => [Array.isArray(value) ? value.map(v=>`${fmt(v)} MW`).join(' – ') : typeof value === 'number' ? `${fmt(value)} MW` : '—', String(name)]} />
        <Area dataKey="range" type="monotone" stroke={CHART_COLORS.adjustment} fill={CHART_COLORS.adjustment} fillOpacity={.12} connectNulls={false} name="P10–P90 scenario"/>
        <Line dataKey="forecast" type="monotone" stroke={CHART_COLORS.baseline} strokeWidth={2.5} dot={false} name="Original forecast"/>
        <Line dataKey="adjusted" type="monotone" stroke={CHART_COLORS.estimate} strokeDasharray="6 4" strokeWidth={2.3} dot={false} name="Validated adjustment"/>
        <Line dataKey="actual" type="monotone" stroke={CHART_COLORS.actual} strokeWidth={2.2} dot={false} name="Actual"/>
      </ComposedChart></ResponsiveContainer></div> : <div className="intel-no-chart">No forecast observations loaded for this date. Use Fetch selected date to import real Elexon records.</div>}
      <div className="intel-chart-legend"><span><i style={{background:CHART_COLORS.baseline}}/>Forecast</span><span><i style={{background:CHART_COLORS.actual}}/>Actual</span><span><i style={{background:CHART_COLORS.adjustment}}/>P10–P90 scenarios</span><span><i style={{background:CHART_COLORS.estimate}}/>Validated adjustment</span></div>
    </div>
    <div className="intel-bottom-grid">
      <div className="panel intel-signals"><div className="panel-head"><div><div className="section-kicker">PLANNING SIGNALS</div><h2>What deserves attention?</h2></div></div>{report.signals.map((signal,i)=><div className={`intel-signal intel-${signal.level}`} key={i}><CircleAlert size={17}/><div><strong>{signal.title}</strong><p>{signal.detail}</p></div></div>)}<div className="intel-smallprint">No demand or power-price input is included. These are wind-generation risk indicators, not buy/sell instructions.</div></div>
      <div className="panel intel-validation"><div className="panel-head"><div><div className="section-kicker">MODEL GOVERNANCE</div><h2>Backtested, not assumed</h2></div></div><div className="intel-compare-row"><span>Unadjusted MAE</span><b>{fmt(gate.baseline_mae_mw)} MW</b></div><div className="intel-compare-row"><span>Candidate corrected MAE</span><b>{fmt(gate.candidate_mae_mw)} MW</b></div><div className="intel-compare-row"><span>Walk-forward decision days</span><b>{gate.tested_days}</b></div><div className="intel-compare-row"><span>Correction enabled</span><b>{gate.adjustment_enabled ? 'Yes' : 'No'}</b></div><p className="intel-explainer">The correction needs ≥4 previous test days, ≥48 scored intervals and at least 1% MAE improvement. It never uses the selected decision date or later days for fitting or approval.</p></div>
    </div>
    <div className="panel intel-table-panel"><div className="panel-head"><div><div className="section-kicker">DELIVERY INTERVAL RISKS</div><h2>Interval-level wind outlook</h2><p>Forecast reliability and historical downside · all quantities in MW</p></div></div><div className="table-scroll"><table><thead><tr><th>DELIVERY UK</th><th>ORIGINAL</th><th>ENGINE MW*</th><th>ACTUAL MW</th><th>ERROR MW</th><th>RESULT</th><th>SCENARIO P10</th><th>PLANNING RESERVE MW</th><th>RISK</th></tr></thead><tbody>{report.profile.length ? report.profile.map(p=><tr key={p.start_time}><td className="bold-cell">{timeOfDay(p.start_time)}</td><td>{fmt(p.raw_forecast_mw)}</td><td>{fmt(p.adjusted_forecast_mw??p.raw_forecast_mw)}</td><td>{fmt(p.actual_mw)}</td><td><b className={p.actual_mw==null?'':p.actual_mw<(p.adjusted_forecast_mw??p.raw_forecast_mw)?'h-bad-number':'h-good-number'}>{signed(p.actual_mw==null?null:p.actual_mw-(p.adjusted_forecast_mw??p.raw_forecast_mw))}</b></td><td>{p.actual_mw==null?<span className="h-signal h-pending">Awaiting actual</span>:p.actual_mw<(p.adjusted_forecast_mw??p.raw_forecast_mw)?<span className="h-signal h-shortfall">Below plan</span>:<span className="h-signal h-surplus">Met/exceeded</span>}</td><td>{fmt(p.p10_actual_mw)}</td><td>{fmt(p.p10_actual_mw==null?null:Math.max((p.adjusted_forecast_mw??p.raw_forecast_mw)-p.p10_actual_mw,0))}</td><td><span className={`intel-risk intel-risk-${p.risk_tier}`}>{riskName(p.risk_tier)}</span></td></tr>) : <tr><td colSpan={9} className="empty-cell">No delivery intervals to score.</td></tr>}</tbody></table></div><div className="table-footer">*Engine power uses a correction only when prior walk-forward evidence supports it; otherwise original Elexon is retained. “No estimate” is not zero risk.</div></div>
    <div className="panel intel-limitations"><strong>Interpretation limits</strong>{report.limitations.map((line,i)=><p key={i}>• {line}</p>)}<p>Historical P10–P90 bands are empirical, not guaranteed probability intervals. Do not sum their endpoints as if they formed a daily forecast distribution.</p></div>
  </div>;
}

function RevisionDrawer({ point, date, time, onClose }: { point: ForecastProfilePoint; date: string; time: string; onClose: () => void }) {
  const [versions, setVersions] = useState<Revision[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => { let live = true; getRevisions(date,time,point.start_time).then(v => { if(live) setVersions(v.versions); }).catch(e => { if (live) setError(e.message); }).finally(() => { if(live) setLoading(false); }); return () => { live = false; }; }, [point,date,time]);
  return <div className="drawer-overlay" onClick={onClose}><aside className="drawer" onClick={e => e.stopPropagation()}><div className="drawer-header"><div><span className="section-kicker">FORECAST AUDIT</span><h2>Revision history</h2></div><button aria-label="Close details" className="icon-button" onClick={onClose}><X size={19}/></button></div><div className="drawer-main"><div className="drawer-summary"><span>Delivery interval</span><strong>{timeStamp(point.start_time)}</strong><div>Selected forecast <b>{fmt(point.forecast_mw)} MW</b></div><div>Observed generation <b>{fmt(point.actual_mw)} MW</b></div></div><h3>Publication timeline</h3><p className="drawer-helper">Only revisions published before the decision cutoff were eligible. All times are shown in UK local time.</p>{loading ? <LoaderCircle className="spin"/> : error ? <p className="danger-text">{error}</p> : versions.length ? <div className="revision-list">{versions.map((version,i) => <div className="revision" key={i}><span className={`revision-dot ${version.eligible ? 'valid' : 'invalid'}`}/><div><b>{fmt(version.generation_mw)} MW</b><span>{timeStamp(version.publish_time)}</span></div><span className={`revision-tag ${version.eligible ? 'eligible' : 'late'}`}>{version.eligible ? 'Eligible' : 'After cutoff'}</span></div>)}</div> : <p>No revisions found for this interval.</p>}</div></aside></div>;
}

export default function App() {
  const [tab, setTab] = useState<Tab>('replay');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [historyVisited, setHistoryVisited] = useState(false);
  const [date, setDate] = useState('2026-01-15');
  const [time, setTime] = useState('09:50');
  const [status, setStatus] = useState<Status | null>(null);
  const [day, setDay] = useState<Comparison | null>(null);
  const [monthly, setMonthly] = useState<Monthly | null>(null);
  const [intelligence, setIntelligence] = useState<Intelligence | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusError, setStatusError] = useState('');
  const [selectedPoint, setSelectedPoint] = useState<ForecastProfilePoint | null>(null);
  const [syncRequest, setSyncRequest] = useState(false);
  const activeRequest = useRef(0);
  useEffect(() => { if(tab === 'history') setHistoryVisited(true); }, [tab]);
  const onForecastImported = useCallback(() => { clearDataCache('main'); }, []);

  const refresh = useCallback(async () => {
    const request = ++activeRequest.current;
    // Only fetch data used by the active analytics tab, never for hidden pages.
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
  async function requestSync() { setSyncRequest(true); try { await prepareForecast(date); await refresh(); } catch (e) { setStatusError(e instanceof Error ? e.message : 'Sync could not be started'); } finally { setSyncRequest(false); } }
  const report = day?.metrics;

  return <div className="app-shell"><Sidebar tab={tab} setTab={setTab} open={mobileOpen} setOpen={setMobileOpen} apiReady={!!status && !statusError}/><main className="main">
    <header className="topbar"><div className="crumbs"><button className="mobile-menu icon-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={21}/></button><span>Workspace</span><span className="crumb-angle">/</span><strong>{tab === 'replay' ? 'Historical replay' : tab === 'live' ? 'Live prediction' : tab === 'history' ? 'History' : tab === 'overview' ? 'Overview' : tab === 'intelligence' ? 'Decision intelligence' : tab === 'records' ? 'Settlement records' : 'Methodology'}</strong></div><div className="topbar-right"><span className="topbar-badge"><span/> {tab === 'live' ? 'Live prediction' : tab === 'history' ? 'Selected history' : tab === 'replay' ? 'Historical replay' : tab === 'overview' ? 'Pilot analytics' : tab === 'intelligence' ? 'Risk intelligence' : tab === 'records' ? 'Data explorer' : 'Methodology'}</span><span className="header-avatar">WS</span></div></header>
    <div className="content">
      <div className="heading-area"><div><div className="eyebrow"><span className="eyebrow-line"/> UK ENERGY MARKET <span className="eyebrow-sep">/</span> WIND GENERATION INTELLIGENCE</div><h1>{tab === 'replay' ? 'Historical forecast replay' : tab === 'live' ? 'Live wind outlook' : tab === 'history' ? 'Historical performance & forecasts' : tab === 'overview' ? 'Wind generation overview' : tab === 'intelligence' ? 'Wind decision intelligence' : tab === 'records' ? 'Settlement records' : 'Forecast methodology'}</h1><p>{tab === 'replay' ? 'Reconstruct yesterday’s decisions and measure wind-side forecast error.' : tab === 'live' ? 'Issue a traceable next-day forecast with advanced shortfall warnings.' : tab === 'history' ? 'Choose any available date range to compare predictions, actuals, error and advance wind contingency.' : tab === 'overview' ? 'Make more confident day-ahead decisions with traceable forecast accuracy.' : tab === 'intelligence' ? 'Explore historical wind downside scenarios and verified forecast corrections.' : tab === 'records' ? 'Inspect every forecast and the actual wind generation behind it.' : 'How each historical day-ahead forecast is reconstructed and evaluated.'}</p></div><div className="heading-action">{tab !== 'replay' && tab !== 'live' && tab !== 'history' && tab !== 'methodology' && <button className="outline-button sync-button" onClick={() => void requestSync()} disabled={syncRequest || !!status?.syncing}><RefreshCw size={16} className={status?.syncing ? 'spin' : ''}/>{status?.syncing ? `Syncing ${status.sync_done}/${status.sync_total}` : 'Fetch selected date'}</button>}</div></div>
      {(tab !== 'replay' && tab !== 'live' && tab !== 'history') && statusError && <div className="notice danger-notice"><CircleAlert size={18}/><span>API connection issue: {statusError}</span><button onClick={() => void refresh()}>Retry</button></div>}
      {(tab === 'overview') && !day?.forecast_profile.length && <div className="notice data-notice"><span className="notice-icon"><Database size={19}/></span><div><strong>{status?.syncing ? 'Importing verified Elexon observations' : (status?.available_days ?? 0) > 0 ? 'Dataset import is partially complete' : 'Historical Elexon data not loaded yet'}</strong><span>{status?.syncing ? `Processing ${status.sync_done} of ${status.sync_total} source-day requests. Only verified records are displayed.` : `Selected day ${date} is not loaded. Use Fetch selected date to download WINDFOR, FUELHH and earlier calibration history.`}</span>{status?.syncing && <div className="notice-progress"><div style={{width:`${status.sync_total ? 100 * status.sync_done / status.sync_total : 0}%`}}/></div>}</div><button className="notice-action" onClick={() => void requestSync()} disabled={syncRequest || !!status?.syncing}>{status?.syncing ? 'Working' : 'Load data'}<ArrowRight size={16}/></button></div>}
      {(tab === 'overview') && !!status?.errors.length && !status.syncing && <div className="notice danger-notice"><CircleAlert size={18}/><span>{status.errors.length} source requests failed. First issue: {status.errors[0]}</span><button onClick={() => void requestSync()}>Retry</button></div>}
      {tab !== 'methodology' && tab !== 'replay' && tab !== 'live' && tab !== 'history' && <div className="filter-row"><div className="filter-text"><Clock3 size={17}/><strong>Decision context</strong><span>Shared with Historical Replay — change date and cutoff there</span></div><div className="filter-controls"><label>Decision date <input type="date" value={date} readOnly aria-label="Shared decision date" title="Change the shared date in Historical Replay" /></label><label>As-of time <span className="select-wrap"><select value={time} disabled aria-label="Shared decision cutoff">{TIME_OPTIONS.map(t => <option value={t} key={t}>{t} UK</option>)}</select><ChevronDown size={14}/></span></label></div></div>}
      {historyVisited && <div style={{display:tab === 'history' ? 'block' : 'none'}}><HistoryPage/></div>}
      <div style={{display:tab === 'replay' ? 'block' : 'none'}}>
        <ForecastWorkspace mode="replay" date={date} decisionTime={time} onDateChange={setDate} onDecisionTimeChange={setTime} onDataImported={onForecastImported}/>
      </div>
      {tab === 'live' ? <ForecastWorkspace mode="live" date={date} decisionTime={time} onDateChange={setDate} onDecisionTimeChange={setTime} onDataImported={onForecastImported}/> : tab === 'replay' || tab === 'history' ? null : tab === 'methodology' ? <Methodology/> : tab === 'intelligence' ? <IntelligencePanel report={intelligence} loading={loading}/> : <>
        {tab === 'overview' && <><div className="h-stats ws-overview-signals"><div><small>Engine forecast · mean</small><strong>{fmt(intelligence?.profile.length ? intelligence.profile.reduce((sum,p)=>sum+(p.adjusted_forecast_mw??p.raw_forecast_mw),0)/intelligence.profile.length : null)} <em>MW</em></strong></div><div><small>Actual wind · mean</small><strong>{fmt(report?.mean_actual_mw)} <em>MW</em></strong></div><div><small>Advance wind planning buffer</small><strong>{fmt(intelligence?.profile.some(p=>p.p10_actual_mw!=null)? intelligence.profile.reduce((sum,p)=>sum+(p.p10_actual_mw==null?0:Math.max((p.adjusted_forecast_mw??p.raw_forecast_mw)-p.p10_actual_mw,0)*p.interval_minutes/60),0):null)} <em>MWh</em></strong></div></div><div className="kpi-grid"><Kpi label="Elexon forecast MAE" value={fmt(report?.mae_mw)} unit="MW" note="Average deviation from actuals" icon={Gauge}/><Kpi label="Root mean square error" value={fmt(report?.rmse_mw)} unit="MW" note="Penalises larger misses" icon={Activity} tone="blue"/><Kpi label="Forecast bias" value={signed(report?.bias_mw)} unit="MW" note="Negative = wind under-delivery" icon={GitCompareArrows} tone="purple"/><Kpi label="Valid interval coverage" value={fmt(report?.coverage_pct,1)} unit={report?.count ? '%' : ''} note={`${fmt(report?.count)} / ${fmt(report?.expected)} delivery intervals`} icon={ShieldCheck} tone="orange"/></div>
        <div className="main-chart-grid"><PowerChart points={day?.forecast_profile ?? []} intelligence={intelligence} loading={loading} matched={day?.points.length ?? 0}/><Exposure comparison={day}/></div>
        <div className="intel-teaser panel"><div><div className="section-kicker">NEW · INTELLIGENCE LAYER</div><h2>From forecast errors to decision evidence</h2><p>Scenario bands, downside flags, and gated historical bias correction — with a chronological backtest.</p></div><button className="primary-intel-button" onClick={() => setTab('intelligence')}>Explore intelligence <ArrowRight size={16}/></button></div>
        <div className="below-chart-grid"><ErrorChart monthly={monthly}/><div className="panel insight-panel"><div className="panel-head"><div><div className="section-kicker">DATA QUALITY</div><h2>Analysis coverage</h2><p>Selected decision history</p></div><span className="round-arrow quality"><ShieldCheck size={19}/></span></div><div className="quality-value"><strong>{fmt(monthly?.metrics.available_days)}<span>/ {monthly?.metrics.total_days ?? 14}</span></strong><span>days with verified source data</span></div><div className="quality-progress"><div style={{width:`${100 * (monthly?.metrics.available_days ?? 0) / (monthly?.metrics.total_days ?? 14)}%`}}/></div><div className="quality-list"><div><Check size={15}/> Publication cutoff enforced</div><div><Check size={15}/> Missing intervals excluded</div><div><Check size={15}/> Actuals aligned in UTC</div></div><button className="quality-link" onClick={() => setTab('methodology')}>How we calculate accuracy <ArrowRight size={16}/></button></div></div></>}
        {tab === 'records' && <div className="records-summary"><div><strong>{fmt(report?.count)}</strong><span>Matched intervals</span></div><div><strong>{fmt(report?.mean_forecast_mw)} <small>MW</small></strong><span>Mean forecast</span></div><div><strong>{fmt(report?.mean_actual_mw)} <small>MW</small></strong><span>Mean actual</span></div><div><strong>{fmt(report?.shortfall_mwh)} <small>MWh</small></strong><span>Wind shortfall exposure</span></div></div>}
        <Table points={day?.forecast_profile ?? []} intelligence={intelligence} date={date} time={time} onVersion={setSelectedPoint}/>
      </>}
      <footer className="page-footer"><span><Wind size={15}/> WindSight · Decision intelligence</span><span>Data: Elexon BMRS · All generation in MW · No inferred demand</span></footer>
    </div>
  </main>{selectedPoint && <RevisionDrawer point={selectedPoint} date={date} time={time} onClose={() => setSelectedPoint(null)}/>}</div>;
}
