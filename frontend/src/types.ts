export interface Metrics {
  count: number; expected: number; coverage_pct: number;
  mae_mw: number | null; rmse_mw: number | null; bias_mw: number | null;
  p90_abs_error_mw: number | null; shortfall_frequency_pct: number | null;
  shortfall_mwh: number | null; mean_forecast_mw: number | null; mean_actual_mw: number | null;
}
export interface Point {
  start_time: string; publish_time: string; forecast_mw: number; actual_mw: number;
  error_mw: number; absolute_error_mw: number; shortfall_mw: number; interval_minutes: number;
}
export interface ForecastProfilePoint {
  start_time: string; publish_time: string; forecast_mw: number; actual_mw: number | null;
  error_mw: number | null; interval_minutes: number;
}
export interface Comparison {
  decision_date: string; delivery_date: string; available: boolean; missing?: string[];
  cutoff_time?: string; resolution_minutes?: number; selected_forecasts?: number;
  invalid_records?: number; actual_observations?: number; missing_actual_intervals?: number; metrics: Metrics; points: Point[]; forecast_profile: ForecastProfilePoint[];
}
export interface Daily extends Metrics { decision_date: string; delivery_date: string; available: boolean; }
export interface Monthly { metrics: Metrics & { available_days: number; total_days: number; missing_days: string[] }; daily: Daily[]; complete: boolean; }
export interface Status { available_days: number; total_days: number; syncing: boolean; sync_done: number; sync_total: number; errors: string[]; source: string; real_data_only: boolean; }
export interface Revision { publish_time: string; generation_mw: number; eligible: boolean; }

export interface IntelligencePoint {
  start_time: string; publish_time: string; raw_forecast_mw: number;
  actual_mw: number | null; interval_minutes: number;
  adjusted_forecast_mw: number | null; candidate_adjusted_mw: number | null;
  p10_actual_mw: number | null; p90_actual_mw: number | null;
  downside_buffer_mw: number | null; shortfall_likelihood_pct: number | null;
  risk_tier: 'elevated' | 'watch' | 'lower' | 'unavailable';
  sample_count: number; sample_days: number; model_source: string;
}
export interface Intelligence {
  decision_date: string; delivery_date: string; cutoff_time: string;
  source: string; status: string; data_complete: boolean;
  training: {sample_intervals:number; sample_days:number; first_decision_date:string|null; last_decision_date:string|null; policy:string};
  backtest: {status:string; adjustment_enabled:boolean; tested_days:number;
    tested_intervals:number; baseline_mae_mw:number|null; candidate_mae_mw:number|null;
    candidate_mae_improvement_pct:number|null; empirical_80pct_band_coverage_pct:number|null; band_note:string};
  summary: {forecast_intervals:number; scored_intervals:number; scenario_intervals:number;
    elevated_risk_intervals:number; raw_forecast_mwh:number|null;
    adjusted_forecast_mwh:number|null; summed_interval_downside_buffer_mwh:number|null;
    buffer_note:string};
  signals: {level:string; title:string; detail:string}[];
  profile: IntelligencePoint[]; limitations:string[];
}

export interface PredictionItem { id:string;created_at:string;decision_date:string;delivery_date:string;interval_count:number; }
export interface PredictionDetails {
  id:string;created_at:string;decision_date:string;delivery_date:string;cutoff_time:string;
  profile: (IntelligencePoint & {prediction_mw:number;raw_error_mw:number|null;prediction_error_mw:number|null})[];
  comparison:{state:string;matched_intervals:number;forecast_intervals:number;actual_source_loaded:boolean;
    baseline:{mae_mw:number|null;rmse_mw:number|null;bias_mw:number|null};engine:{mae_mw:number|null;rmse_mw:number|null;bias_mw:number|null}};
}

export interface HistoryInterval {
  start_time:string; publish_time:string; interval_minutes:number;
  baseline_mw:number; predicted_mw:number; actual_mw:number|null; error_mw:number|null;
  result:'shortfall'|'surplus'|'pending'; planning_buffer_mw:number|null;
  planning_buffer_mwh:number|null; observed_shortfall_mwh:number|null; risk_tier:string;
}
export interface HistoryDay {
  decision_date:string; delivery_date:string; cutoff_time:string;
  model_status:string; adjustment_enabled:boolean;
  forecast_intervals:number; scored_intervals:number; risk_coverage_intervals:number;
  mean_prediction_mw:number|null; mean_actual_mw:number|null; mae_mw:number|null; bias_mw:number|null;
  planned_buffer_mwh:number|null; observed_shortfall_mwh:number|null;
  shortfall_intervals:number; surplus_intervals:number;
  missing:string[]; intervals:HistoryInterval[];
}
export interface HistoryResult {
  start:string; end:string; page:number; page_size:number; total_days:number; total_pages:number;
  days:HistoryDay[]; planning_note:string;
}
