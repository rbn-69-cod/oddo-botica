const LIMA_TIME_ZONE = 'America/Lima';
const LIMA_OFFSET = '-05:00';

/** Interpreta las fechas sin zona del backend como hora local de Lima. */
export function parseBackendDate(value: string): Date {
  if (!value) return new Date(NaN);
  const hasTimeZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
  return new Date(hasTimeZone ? value : `${value}${LIMA_OFFSET}`);
}

export function formatDateTime(value: string, includeSeconds = false): string {
  const date = parseBackendDate(value);
  if (Number.isNaN(date.getTime())) return 'Fecha no disponible';

  return new Intl.DateTimeFormat('es-PE', {
    timeZone: LIMA_TIME_ZONE,
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    ...(includeSeconds ? { second: '2-digit' as const } : {})
  }).format(date);
}

export function formatRelativeTime(value: string): string {
  const date = parseBackendDate(value);
  if (Number.isNaN(date.getTime())) return 'Sin fecha';

  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const absoluteSeconds = Math.abs(seconds);
  if (absoluteSeconds < 60) return 'Ahora mismo';

  const formatter = new Intl.RelativeTimeFormat('es', { numeric: 'always' });
  if (absoluteSeconds < 3600) return formatter.format(Math.round(seconds / 60), 'minute');
  if (absoluteSeconds < 86400) return formatter.format(Math.round(seconds / 3600), 'hour');
  if (absoluteSeconds < 2592000) return formatter.format(Math.round(seconds / 86400), 'day');
  return formatter.format(Math.round(seconds / 2592000), 'month');
}
