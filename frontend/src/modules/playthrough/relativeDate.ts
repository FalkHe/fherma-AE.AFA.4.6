// One "Created <relative date>" formatter for the dashboard's cards (sprint
// 007/07 WI1, AC2). `Intl.RelativeTimeFormat` is a built-in — no date
// library, no new dependency (sprint brief's "Decided for you"). Walks
// year/month/week/day/hour/minute thresholds down to "second", picking the
// coarsest unit the elapsed time still fills.
const UNIT_SECONDS: ReadonlyArray<readonly [Intl.RelativeTimeFormatUnit, number]> = [
  ["year", 60 * 60 * 24 * 365],
  ["month", 60 * 60 * 24 * 30],
  ["week", 60 * 60 * 24 * 7],
  ["day", 60 * 60 * 24],
  ["hour", 60 * 60],
  ["minute", 60],
];

export function formatRelativeDate(createdAt: string, locale: string): string {
  const seconds = (Date.parse(createdAt) - Date.now()) / 1000;
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });

  for (const [unit, secondsInUnit] of UNIT_SECONDS) {
    if (Math.abs(seconds) >= secondsInUnit) {
      return formatter.format(Math.round(seconds / secondsInUnit), unit);
    }
  }
  return formatter.format(Math.round(seconds), "second");
}
