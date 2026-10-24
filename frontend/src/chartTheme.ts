export const CHART_COLORS = {
  baseline: '#2563eb',
  estimate: '#0f766e',
  actual: '#ea580c',
  upper: '#16a34a',
  lower: '#dc2626',
  scenarioFill: '#86efac',
  adjustment: '#7c3aed',
  barLow: '#16a34a',
  barMedium: '#d97706',
  barHigh: '#dc2626',
  axis: '#6f8178',
};

export const tooltipBoxStyle = {
  borderRadius: 12,
  border: '1px solid #d9e6df',
  boxShadow: '0 12px 26px rgba(18, 56, 44, 0.16)',
  fontSize: 11,
  background: '#ffffff',
};

export function formatUkDateTime(value: string, withZone = true): string {
  return new Date(value).toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Europe/London',
    ...(withZone ? { timeZoneName: 'short' } : {}),
  });
}

export function formatUkTime(value: string): string {
  return new Date(value).toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Europe/London',
  });
}

export function formatUkAxisTick(value: string): string {
  return new Date(value).toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Europe/London',
  });
}

export function formatUkDate(value: string): string {
  return new Date(value).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    timeZone: 'Europe/London',
  });
}

export function formatMwTick(value: number): string {
  return `${(value / 1000).toFixed(1)}k`;
}

export function getDailyErrorColor(value: number | null | undefined): string {
  if (value == null) return '#d8e3dd';
  if (value <= 1500) return CHART_COLORS.barLow;
  if (value <= 3000) return CHART_COLORS.barMedium;
  return CHART_COLORS.barHigh;
}
