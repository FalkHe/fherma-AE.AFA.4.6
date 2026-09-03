/**
 * The tool-result shapes the four styled renderers consume, and the shape
 * checks that decide whether they may.
 *
 * `toolCalls[].result` is an **open object** in the generated client — every
 * tool has its own result schema and the backend may grow tools this frontend
 * has never heard of. Dispatch is therefore a *shape check* (never a try/catch
 * around rendering): a result that matches the pinned schema
 * (shared-knowledge §"Tool result schemas") gets its styled renderer, anything
 * else — a future tool, a failed call, or the shared name-resolution failure
 * `{"unknownBike": "…"}` — falls through to the generic key/value table, so
 * every executed tool call stays visible.
 *
 * Each check verifies exactly the fields its renderer reads, with the pinned
 * types. Fields nobody renders are deliberately not part of the parsed type:
 * a result missing one of those must not cost the customer the styled block.
 */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isArrayOf<T>(
  value: unknown,
  isItem: (item: unknown) => item is T,
): value is T[] {
  return Array.isArray(value) && value.every(isItem);
}

function isNullableNumber(value: unknown): value is number | null | undefined {
  return value === null || value === undefined || typeof value === "number";
}

function isNullableString(value: unknown): value is string | null | undefined {
  return value === null || value === undefined || typeof value === "string";
}

/** One hit of `catalogue_search`, with the key specs the list line shows. */
export type CatalogueSearchHit = {
  motorbikeId: string;
  name: string;
  category?: string | null;
  powerKw?: number | null;
  wetWeightKg?: number | null;
};

export type CatalogueSearchResult = { results: CatalogueSearchHit[] };

function isCatalogueSearchHit(value: unknown): value is CatalogueSearchHit {
  return (
    isRecord(value) &&
    typeof value.motorbikeId === "string" &&
    typeof value.name === "string" &&
    isNullableString(value.category) &&
    isNullableNumber(value.powerKw) &&
    isNullableNumber(value.wetWeightKg)
  );
}

export function isCatalogueSearchResult(value: unknown): value is CatalogueSearchResult {
  return isRecord(value) && isArrayOf(value.results, isCatalogueSearchHit);
}

/** One column of the comparison table. */
export type ComparisonBike = { motorbikeId: string; name: string };

/**
 * One row: a frozen camelCase spec field name and one value per bike, aligned
 * to the `bikes` order. A value may be anything JSON — `null` is the honest
 * answer for a spec that was never verified.
 */
export type ComparisonRow = { field: string; values: unknown[] };

export type SpecComparisonResult = { bikes: ComparisonBike[]; rows: ComparisonRow[] };

function isComparisonBike(value: unknown): value is ComparisonBike {
  return (
    isRecord(value) &&
    typeof value.motorbikeId === "string" &&
    typeof value.name === "string"
  );
}

function isComparisonRow(value: unknown): value is ComparisonRow {
  return isRecord(value) && typeof value.field === "string" && Array.isArray(value.values);
}

export function isSpecComparisonResult(value: unknown): value is SpecComparisonResult {
  return (
    isRecord(value) &&
    isArrayOf(value.bikes, isComparisonBike) &&
    isArrayOf(value.rows, isComparisonRow)
  );
}

/** The three verdicts a licence/fit rule can reach; `unknown` is not a failure. */
export const LICENCE_VERDICTS = ["pass", "fail", "unknown"] as const;

export type LicenceVerdict = (typeof LICENCE_VERDICTS)[number];

/**
 * One checked rule. `label` and `evidence` are server-composed English strings
 * rendered verbatim (the same i18n exemption as operation messages); the
 * evidence is the visible arithmetic behind the verdict.
 */
export type LicenceFitRule = {
  rule: string;
  label: string;
  verdict: LicenceVerdict;
  evidence?: string | null;
};

export type LicenceFitCheckResult = { rules: LicenceFitRule[] };

function isLicenceVerdict(value: unknown): value is LicenceVerdict {
  return (LICENCE_VERDICTS as readonly unknown[]).includes(value);
}

function isLicenceFitRule(value: unknown): value is LicenceFitRule {
  return (
    isRecord(value) &&
    typeof value.rule === "string" &&
    typeof value.label === "string" &&
    isLicenceVerdict(value.verdict) &&
    isNullableString(value.evidence)
  );
}

export function isLicenceFitCheckResult(value: unknown): value is LicenceFitCheckResult {
  return isRecord(value) && isArrayOf(value.rules, isLicenceFitRule);
}

/** One line of the cost estimate; the label (incl. any "/year") is verbatim. */
export type CostLineItem = { label: string; amount: number };

/**
 * `usedPrice` is additive (shared-knowledge D11, ui-spec §4.3/§8 API-4). Its
 * shape is validated by `UsedPriceSnapshot`'s own guard, not here — a malformed
 * or absent `usedPrice` must not cost the rest of this result its styled
 * renderer, so it is deliberately typed `unknown` at this layer and passed
 * through unchecked.
 */
export type CostEstimatorResult = {
  currency: string;
  lineItems: CostLineItem[];
  total: number;
  assumptions: string[];
  usedPrice?: unknown;
};

function isCostLineItem(value: unknown): value is CostLineItem {
  return (
    isRecord(value) && typeof value.label === "string" && typeof value.amount === "number"
  );
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

export function isCostEstimatorResult(value: unknown): value is CostEstimatorResult {
  return (
    isRecord(value) &&
    // `Intl.NumberFormat` throws on anything that is not an ISO-4217 code, and
    // the check is the only thing standing between that and a blank bubble.
    typeof value.currency === "string" &&
    /^[A-Za-z]{3}$/.test(value.currency) &&
    isArrayOf(value.lineItems, isCostLineItem) &&
    typeof value.total === "number" &&
    isArrayOf(value.assumptions, isString)
  );
}

/** How firmly a captured preference is held. */
export const PREFERENCE_FIRMNESS = ["hard", "soft", "exploring"] as const;

export type PreferenceFirmness = (typeof PREFERENCE_FIRMNESS)[number];

export type RecordPreferenceResult = {
  attribute: string;
  value: string;
  firmness: PreferenceFirmness;
};

function isPreferenceFirmness(value: unknown): value is PreferenceFirmness {
  return (PREFERENCE_FIRMNESS as readonly unknown[]).includes(value);
}

export function isRecordPreferenceResult(value: unknown): value is RecordPreferenceResult {
  return (
    isRecord(value) &&
    typeof value.attribute === "string" &&
    typeof value.value === "string" &&
    isPreferenceFirmness(value.firmness)
  );
}

export type FlagUnknownBikeResult = { name: string };

export function isFlagUnknownBikeResult(value: unknown): value is FlagUnknownBikeResult {
  return isRecord(value) && typeof value.name === "string";
}
