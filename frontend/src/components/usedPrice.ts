/**
 * The D11 wire shape (shared-knowledge D11, ui-spec §4.1/§8 API-3/API-4) and
 * its runtime guard — split out of `UsedPriceSnapshot.tsx` itself, which
 * `react-refresh/only-export-components` restricts to component exports only.
 */

/** One source backing the snapshot — always rendered as a visible external link. */
export type UsedPriceSource = { title: string; url: string };

/**
 * `sampleCount: null` means unknown, never zero (shared-knowledge D8/D11).
 */
export type UsedPrice = {
  medianEur: number;
  minEur: number;
  maxEur: number;
  sampleCount: number | null;
  asOf: string;
  stale: boolean;
  sources: UsedPriceSource[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isUsedPriceSource(value: unknown): value is UsedPriceSource {
  return (
    isRecord(value) && typeof value.title === "string" && typeof value.url === "string"
  );
}

/**
 * The malformed guard (§4.1): a price without provenance would read as a fact,
 * which is the one forbidden state. Anything short of the full, correctly typed
 * shape — including an empty `sources` — fails this check, and the component
 * renders nothing rather than guessing or throwing.
 */
export function isUsedPrice(value: unknown): value is UsedPrice {
  return (
    isRecord(value) &&
    typeof value.medianEur === "number" &&
    typeof value.minEur === "number" &&
    typeof value.maxEur === "number" &&
    (value.sampleCount === null || typeof value.sampleCount === "number") &&
    typeof value.asOf === "string" &&
    typeof value.stale === "boolean" &&
    Array.isArray(value.sources) &&
    value.sources.length > 0 &&
    value.sources.every(isUsedPriceSource)
  );
}
