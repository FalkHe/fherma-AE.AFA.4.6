import type { TFunction } from "i18next";

import type { Manufacturer } from "../hooks/useCatalogueModels";
import type { ProductSuggestion } from "../hooks/useProductReview";

/**
 * Pure "use the claim" logic for `ModelClaimPanel`/`ModelIdentityPanel` (ui-spec
 * §2.3), split into its own module — not because the D6 component boundary
 * requires it (these are plain functions, not components that accept claim
 * data for rendering), but because a file mixing components and other exports
 * breaks React Fast Refresh (`react-refresh/only-export-components`). The
 * component boundary itself is documented on `ModelClaimPanel.tsx`.
 */

/**
 * The manufacturer claim row's button only ever appears when a case-insensitive
 * match exists in the curated options (§2.3) — the manufacturer table is
 * curated, so the form cannot invent a row.
 */
export function matchManufacturerClaim(
  suggestion: ProductSuggestion,
  options: readonly Manufacturer[],
): Manufacturer | null {
  if (suggestion.manufacturer === null) {
    return null;
  }

  const claimed = suggestion.manufacturer.toLowerCase();

  return options.find((option) => option.name.toLowerCase() === claimed) ?? null;
}

/**
 * "Use claim" on the year fields fills both at once, mirroring the import's
 * own collapse rule: `yearFrom` is the earliest of every claimed range,
 * `yearTo` is `null` when the claim says the model is still in production,
 * else the latest end year.
 */
export function collapseClaimedYears(
  suggestion: ProductSuggestion,
): { yearFrom: number; yearTo: number | null } | null {
  // `SuggestionYearRange.from`/`.to` are both `number | null` on the wire
  // (a range with no known start is not itself impossible), so a range
  // missing `from` cannot anchor the collapse and is dropped.
  const froms =
    suggestion.yearRanges.length > 0
      ? suggestion.yearRanges
          .map((range) => range.from)
          .filter((from): from is number => from !== null && from !== undefined)
      : suggestion.yearFrom !== null
        ? [suggestion.yearFrom]
        : [];

  if (froms.length === 0) {
    return null;
  }

  const yearFrom = Math.min(...froms);

  if (suggestion.inProduction) {
    return { yearFrom, yearTo: null };
  }

  const tos =
    suggestion.yearRanges.length > 0
      ? suggestion.yearRanges
          .map((range) => range.to ?? range.from)
          .filter((to): to is number => to !== null && to !== undefined)
      : suggestion.yearTo !== null
        ? [suggestion.yearTo]
        : [];

  return { yearFrom, yearTo: tos.length > 0 ? Math.max(...tos) : null };
}

/** One claimed year span, formatted like the CLI summary (`2019–2023`, `from 2019`). */
function formatYearSpan(t: TFunction, from: number, to: number | null): string {
  if (to === null) {
    return t("common.modelName.yearFrom", { from });
  }
  if (to === from) {
    return t("common.modelName.yearSingle", { year: from });
  }
  return t("common.modelName.yearRange", { from, to });
}

/**
 * The year claim row's caption: the primary claimed range, or every entry of
 * `year_ranges` joined when there is more than one (§2.3).
 */
export function formatClaimedYears(t: TFunction, suggestion: ProductSuggestion): string | null {
  if (suggestion.yearRanges.length > 1) {
    // A range with no `from` at all carries nothing to render — dropped
    // rather than shown as a blank span.
    return suggestion.yearRanges
      .filter(
        (range): range is { from: number; to: number | null } =>
          range.from !== null && range.from !== undefined,
      )
      .map((range) => formatYearSpan(t, range.from, range.to ?? null))
      .join(" · ");
  }

  if (suggestion.yearFrom === null && suggestion.yearTo === null) {
    return null;
  }

  if (suggestion.yearFrom !== null && suggestion.yearTo !== null) {
    return formatYearSpan(t, suggestion.yearFrom, suggestion.yearTo);
  }

  if (suggestion.yearFrom !== null) {
    return t("common.modelName.yearFrom", { from: suggestion.yearFrom });
  }

  return t("common.modelName.yearUntil", { to: suggestion.yearTo });
}

/** The type-codes claim caption: every claimed code, joined per §2.3. */
export function formatClaimedTypeCodes(suggestion: ProductSuggestion): string {
  return suggestion.typeCodes.join("/");
}

/**
 * Unions claimed type codes into the current chip list, dropping codes already
 * present (pre-normalised by the import) and refusing any that would exceed
 * the cap of 8 — the field then shows `typeCodesMax` (§2.3).
 */
export function unionTypeCodes(
  current: readonly string[],
  claimed: readonly string[],
): { codes: string[]; capped: boolean } {
  const codes = [...current];
  let capped = false;

  for (const code of claimed) {
    if (codes.includes(code)) {
      continue;
    }
    if (codes.length >= 8) {
      capped = true;
      continue;
    }
    codes.push(code);
  }

  return { codes, capped };
}
