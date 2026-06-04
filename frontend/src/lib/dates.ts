export function isoDate(value = new Date()): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function addDays(date: string, days: number): string {
  const next = new Date(`${date}T12:00:00`);
  next.setDate(next.getDate() + days);
  return isoDate(next);
}

export function weekStart(date = isoDate()): string {
  const current = new Date(`${date}T12:00:00`);
  const day = current.getDay();
  const mondayOffset = day === 0 ? -6 : 1 - day;
  current.setDate(current.getDate() + mondayOffset);
  return isoDate(current);
}

/** Monday..Saturday (6 work-days) of the week containing `date`. */
export function monSatWeek(date = isoDate()): { from: string; to: string } {
  const from = weekStart(date);
  return { from, to: addDays(from, 5) };
}

/** First..last calendar day of the month containing `date`. */
export function monthRange(date = isoDate()): { from: string; to: string } {
  const base = new Date(`${date}T12:00:00`);
  const first = new Date(base.getFullYear(), base.getMonth(), 1, 12);
  const last = new Date(base.getFullYear(), base.getMonth() + 1, 0, 12);
  return { from: isoDate(first), to: isoDate(last) };
}

export function shortDate(date: string): string {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(
    new Date(`${date}T12:00:00`)
  );
}

export function shortTime(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

/**
 * Parse a backend timestamp. Some are serialized as naive UTC (no `Z`/offset, e.g.
 * project last_activity/log times via utc_now()); JS would otherwise read those as
 * *local* time and be hours off. Treat a designator-less ISO string as UTC.
 */
export function parseServerDate(iso: string): Date {
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  return new Date(hasTz ? iso : `${iso}Z`);
}

