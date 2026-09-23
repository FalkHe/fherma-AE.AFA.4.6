// A small formatting helper shared by `NarrationRow` and `PlayerRow`
// (sprint 010/06 WI2): D12's rows carry a wall-clock time (e.g. "21:02"),
// never a date -- `Intl.DateTimeFormat` is a browser built-in, no date
// library added (same precedent as `playthrough/relativeDate.ts`'s
// `Intl.RelativeTimeFormat`).
export function formatClockTime(at: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", hour12: false }).format(
    new Date(at),
  );
}
