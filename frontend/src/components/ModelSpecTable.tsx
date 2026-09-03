import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { Fragment } from "react";
import { useTranslation } from "react-i18next";

import type { CatalogueModelDetail, CatalogueVariant } from "../hooks/useCatalogueModel";

import {
  formatSpecEnum,
  formatSpecValue,
  formatVariantDeltaLine,
  specFieldLabel,
  specFieldUnit,
  type SpecFieldKey,
} from "./specFields";

/**
 * The verified specification of one model (ui-spec §4.3): the 13 frozen fields
 * in four groups.
 *
 * **Null discipline (the decision that shapes this file):** an unknown field
 * renders *no row*, and a group whose fields are all unknown renders *no
 * header*. This is a customer sales surface — an em-dashed row of unknowns is
 * noise here, unlike the chat comparison table, where columns must stay aligned
 * across bikes. A model whose extraction produced nothing at all says so in one
 * sentence instead of showing an empty table.
 *
 * Labels, units and values come from `specFields.ts` — there is exactly one spec
 * label table in this application, and it is not this file.
 */

type SpecGroup = {
  /** Suffix of `catalogue.detail.groups.*`. */
  key: "engine" | "chassis" | "safety" | "market";
  fields: readonly SpecFieldKey[];
};

/**
 * The binding group → field mapping (ui-spec §4.3). Every one of the 13 frozen
 * keys appears exactly once; the co-located test asserts the rendered rows
 * against `SPEC_FIELD_KEYS`, so a field added to the contract cannot silently
 * vanish from this page.
 */
const SPEC_GROUPS: readonly SpecGroup[] = [
  {
    key: "engine",
    fields: ["engineCc", "cylinders", "powerKw", "torqueNm", "topSpeedKmh"],
  },
  { key: "chassis", fields: ["wetWeightKg", "seatHeightMm", "tankCapacityL"] },
  { key: "safety", fields: ["abs", "a2Eligible"] },
  { key: "market", fields: ["category", "priceBand", "msrpEur"] },
];

type Specs = CatalogueModelDetail["specs"];

export function ModelSpecTable({
  specs,
  variants,
}: {
  specs: Specs;
  /**
   * The row's trims (data-model §2.5, ui-spec §3.2/§6.5) — optional so a
   * payload that predates step 6.23 (today's) renders exactly as before.
   */
  variants?: CatalogueVariant[];
}) {
  const { t, i18n } = useTranslation();

  /**
   * The list price is the one field not rendered through `formatSpecValue`: a
   * price is currency, not a number with a unit suffix (project-wide EUR pin).
   */
  function formatValue(field: SpecFieldKey): string | null {
    if (field === "msrpEur") {
      return specs.msrpEur === null
        ? null
        : new Intl.NumberFormat(i18n.language, {
            style: "currency",
            currency: "EUR",
            maximumFractionDigits: 0,
          }).format(specs.msrpEur);
    }
    if (field === "category") {
      return specs.category === null ? null : formatSpecEnum(t, field, specs.category);
    }
    if (field === "priceBand") {
      return specs.priceBand === null ? null : formatSpecEnum(t, field, specs.priceBand);
    }

    const formatted = formatSpecValue(t, specs[field]);

    if (formatted === null) {
      return null;
    }
    const unit = specFieldUnit(t, field);

    return unit === "" ? formatted : `${formatted} ${unit}`;
  }

  const groups = SPEC_GROUPS.map((group) => ({
    key: group.key,
    rows: group.fields
      .map((field) => ({ field, value: formatValue(field) }))
      .filter((row): row is { field: SpecFieldKey; value: string } => row.value !== null),
  })).filter((group) => group.rows.length > 0);

  // The trims group (ui-spec §3.2, display-spec §6.5): one row per trim that
  // carries `specs` (a description-only trim is chip-row-only, no table row);
  // never phrased as a filter promise — the group heading is "Trims", not
  // "Also available with…" (D4's known gap).
  const variantRows = (variants ?? [])
    .filter((variant) => variant.specs !== null && Object.keys(variant.specs).length > 0)
    .map((variant) => ({
      slug: variant.slug,
      name: variant.name,
      delta: formatVariantDeltaLine(t, variant.specs ?? {}),
    }))
    .filter((row) => row.delta !== "");

  return (
    <>
      <Typography variant="h5" component="h2" sx={{ mb: 1 }}>
        {t("catalogue.detail.specsHeading")}
      </Typography>
      {groups.length === 0 && variantRows.length === 0 ? (
        // Approved without a verified revision: unusual, but legal.
        <Typography variant="body2" color="text.secondary">
          {t("catalogue.detail.noSpecs")}
        </Typography>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label={t("catalogue.detail.specsTableLabel")}>
            <TableBody>
              {groups.map((group) => (
                <Fragment key={group.key}>
                  <TableRow>
                    <TableCell colSpan={2} sx={{ bgcolor: "action.hover" }}>
                      <Typography variant="subtitle2">
                        {t(`catalogue.detail.groups.${group.key}`)}
                      </Typography>
                    </TableCell>
                  </TableRow>
                  {group.rows.map((row) => (
                    <TableRow key={row.field}>
                      <TableCell component="th" scope="row" sx={{ width: "55%" }}>
                        {specFieldLabel(t, row.field)}
                      </TableCell>
                      <TableCell>{row.value}</TableCell>
                    </TableRow>
                  ))}
                </Fragment>
              ))}
              {variantRows.length > 0 && (
                <Fragment key="trims">
                  <TableRow>
                    <TableCell colSpan={2} sx={{ bgcolor: "action.hover" }}>
                      <Typography variant="subtitle2">
                        {t("catalogue.detail.trims.heading")}
                      </Typography>
                    </TableCell>
                  </TableRow>
                  {variantRows.map((row) => (
                    <TableRow key={row.slug}>
                      <TableCell component="th" scope="row" sx={{ width: "55%", fontWeight: 600 }}>
                        {row.name}
                      </TableCell>
                      <TableCell>{row.delta}</TableCell>
                    </TableRow>
                  ))}
                </Fragment>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </>
  );
}
