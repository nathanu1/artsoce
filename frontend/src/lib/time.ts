// Simulation times are naive ISO strings in the town's own clock; format them without a time
// zone conversion (treat as UTC on both ends).

const parse = (iso: string) => new Date(iso.length === 19 ? `${iso}Z` : iso);

const timeFmt = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", timeZone: "UTC" });
const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "short", day: "numeric", timeZone: "UTC" });
const dateFmt = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
const shortDay = new Intl.DateTimeFormat(undefined, { weekday: "short", timeZone: "UTC" });
const num = new Intl.NumberFormat();
const dec2 = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const formatTime = (iso: string) => timeFmt.format(parse(iso));
export const formatDay = (iso: string) => dayFmt.format(parse(iso));
/** "Mon, Feb 13": the clock's compact date. */
export const formatDate = (iso: string) => dateFmt.format(parse(iso));
export const formatShortDay = (iso: string) => shortDay.format(parse(iso));
export const formatNumber = (n: number) => num.format(n);
export const formatDecimal = (n: number) => dec2.format(n);
/** "Mon 9:40 AM" in the reader's locale. */
export const formatDayTime = (iso: string) => `${shortDay.format(parse(iso))} ${timeFmt.format(parse(iso))}`;

export function hourOf(iso: string): number {
  const d = parse(iso);
  return d.getUTCHours() + d.getUTCMinutes() / 60;
}

export function minutesBetween(a: string, b: string): number {
  return (parse(b).getTime() - parse(a).getTime()) / 60000;
}

export function addMinutes(iso: string, minutes: number): string {
  return new Date(parse(iso).getTime() + minutes * 60000).toISOString().slice(0, 19);
}

export function isBefore(a: string, b: string): boolean {
  return parse(a).getTime() < parse(b).getTime();
}
