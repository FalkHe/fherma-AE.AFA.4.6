import type { TFunction } from "i18next";

/**
 * Display helpers for the frozen specification fields.
 *
 * A spec comparison row, a catalogue-search hit and a recommendation card all
 * label the same numbers, and the labels are keyed by the **frozen camelCase
 * spec column names** the backend sends (shared-knowledge §"Tool result
 * schemas"). Those names are the contract, so the mapping to a human label and
 * a unit lives in exactly one place — and a field this frontend predates falls
 * back to the key verbatim rather than to a raw i18n key on screen.
 */

/**
 * Every frozen spec column, in the order the backend's comparison tool emits
 * them. `consultations.specFields.*` must have an entry for each — the spec
 * comparison test asserts it.
 */
export const SPEC_FIELD_KEYS = [
  "category",
  "engineCc",
  "cylinders",
  "powerKw",
  "torqueNm",
  "wetWeightKg",
  "seatHeightMm",
  "tankCapacityL",
  "topSpeedKmh",
  "abs",
  "a2Eligible",
  "priceBand",
  "msrpEur",
] as const;

export type SpecFieldKey = (typeof SPEC_FIELD_KEYS)[number];

/** The fields that carry a unit; the others (enums, flags, counts) do not. */
const SPEC_FIELD_UNITS = {
  engineCc: "cc",
  powerKw: "kw",
  torqueNm: "nm",
  wetWeightKg: "kg",
  seatHeightMm: "mm",
  tankCapacityL: "l",
  topSpeedKmh: "kmh",
  msrpEur: "eur",
} as const satisfies Partial<Record<SpecFieldKey, string>>;

type UnitedSpecFieldKey = keyof typeof SPEC_FIELD_UNITS;

export function isSpecFieldKey(field: string): field is SpecFieldKey {
  return (SPEC_FIELD_KEYS as readonly string[]).includes(field);
}

function hasUnit(field: string): field is UnitedSpecFieldKey {
  return field in SPEC_FIELD_UNITS;
}

/** The human label of a spec field; an unmapped key renders verbatim. */
export function specFieldLabel(t: TFunction, field: string): string {
  return isSpecFieldKey(field) ? t(`consultations.specFields.${field}`) : field;
}

/** The unit of a spec field, or `""` for the fields that have none. */
export function specFieldUnit(t: TFunction, field: string): string {
  return hasUnit(field) ? t(`consultations.specUnits.${SPEC_FIELD_UNITS[field]}`) : "";
}

/**
 * The customer-facing label of a `category` / `priceBand` enum value.
 *
 * The vocabularies are pinned by the backend, so the labels live in one hoisted
 * block (`common.specEnums.*`) shared by the admin spec form and the catalogue
 * screens. A value this frontend predates renders **verbatim** rather than as a
 * raw i18n key — forward compatibility beats a pretty label.
 *
 * Deliberately not used on chat surfaces: tool results render backend values
 * verbatim (the Phase-3 tool-value exemption, unchanged).
 */
export function formatSpecEnum(
  t: TFunction,
  field: "category" | "priceBand",
  value: string,
): string {
  return t(`common.specEnums.${field}.${value}`, { defaultValue: value });
}

/**
 * A trim's spec deltas (`variants[].specs`, data-model §2.5) as one composed
 * line — `"Tank capacity: 30 l · Wet weight: 268 kg"` — the same
 * label-and-unit idiom `CatalogueModelCard`/`RecommendationCard` already use,
 * reused here so the customer trims group (`ModelSpecTable`) and the admin
 * read-only trim card (`ModelIdentityPanel`, approved rows) render the same
 * string for the same data. An unrecognised key is skipped (never rendered
 * verbatim into a labelled sentence); an entry that produces nothing (a null
 * value, an empty string) is dropped rather than shown as a blank segment.
 */
export function formatVariantDeltaLine(
  t: TFunction,
  specs: Partial<Record<string, unknown>>,
): string {
  return Object.entries(specs)
    .filter((entry): entry is [SpecFieldKey, unknown] => isSpecFieldKey(entry[0]))
    .map(([field, value]) => {
      const formatted =
        (field === "category" || field === "priceBand") && typeof value === "string"
          ? formatSpecEnum(t, field, value)
          : formatSpecValue(t, value);

      if (formatted === null) {
        return null;
      }

      const unit = specFieldUnit(t, field);
      const withUnit = unit === "" ? formatted : `${formatted} ${unit}`;

      return `${specFieldLabel(t, field)}: ${withUnit}`;
    })
    .filter((line): line is string => line !== null)
    .join(" · ");
}

/**
 * One spec value as text, or `null` when there is nothing verified to show —
 * the caller renders the em dash, because "unknown" needs its own markup
 * (`aria-label`) in a table cell and none at all in a card line.
 *
 * A missing verified spec stays missing: this function never substitutes a
 * default. Enum values (category, price band) come from the backend and are
 * rendered verbatim, like every other tool-result value.
 */
export function formatSpecValue(t: TFunction, value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value === "boolean") {
    return value ? t("common.yes") : t("common.no");
  }
  if (typeof value === "number") {
    return String(value);
  }
  if (typeof value === "string") {
    return value === "" ? null : value;
  }

  // Not a scalar — a shape the frozen fields do not produce. Showing the JSON
  // is still better than showing nothing.
  return JSON.stringify(value);
}
