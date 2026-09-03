import { zodResolver } from "@hookform/resolvers/zod";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Grid from "@mui/material/Grid";
import Icon from "@mui/material/Icon";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import MenuItem from "@mui/material/MenuItem";
import Skeleton from "@mui/material/Skeleton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import type { TFunction } from "i18next";
import { useEffect, useRef, useState } from "react";
import {
  Controller,
  useFieldArray,
  useForm,
  useWatch,
  type Control,
  type UseFormReturn,
} from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

import { useBuildinglines } from "../hooks/useBuildinglines";
import { useManufacturers, type Manufacturer } from "../hooks/useCatalogueModels";
import type { Operation } from "../hooks/useOperations";
import {
  SaveIdentityError,
  useSaveIdentity,
  type DraftSpec,
  type VariantWrite,
} from "../hooks/useProductReview";
import type { Product } from "../hooks/useProducts";

import {
  collapseClaimedYears,
  formatClaimedTypeCodes,
  formatClaimedYears,
  matchManufacturerClaim,
  unionTypeCodes,
} from "./claimLogic";
import { ClaimFieldRow, ModelClaimPanel } from "./ModelClaimPanel";
import { formatVariantDeltaLine } from "./specFields";

/**
 * The Identity tab (roadmap 6.1/6.3, ui-spec §1 + §2, display-spec §6.2): the
 * manufacturer/buildingline/model-name/year-range/type-codes form, the
 * unverified claim above it, and the live level-1/level-2 preview.
 *
 * Mirrors `ModelSpecsPanel`'s shape (React Hook Form + Zod, submit-only
 * validation, explicit save, dirty state reported upward) and, like it, edits
 * a full-object-replace block: the identity PATCH always carries every
 * identity field, and (until step 6.25 builds the trims editor) the last
 * fetched `variants` list unchanged — see `useSaveIdentity`.
 */

// Duplicated from `backend/app/services/ingestion/service.py:76` — a fragile
// string contract (ui-spec §2.4 / API-7, shared-knowledge D13, OQ-2). A
// backend rename of this prefix must update both locations.
const WARNING_SUMMARY_PREFIX = "Completed with warnings: ";

const TYPE_CODE_PATTERN = /^[A-Z0-9][A-Z0-9\-/ ]{1,31}$/;
const TYPE_CODES_CAP = 8;
const CURRENT_YEAR = new Date().getFullYear();

/** Trimmed on entry, empty string becomes `null` — the shared string rule of §1.3. */
function trimmedNullable(maxLength: number, errorMessage: string) {
  return z
    .string()
    .transform((raw) => raw.trim())
    .transform((raw) => (raw === "" ? null : raw))
    .refine((value) => value === null || value.length <= maxLength, {
      message: errorMessage,
    });
}

/** Empty → `null`; else a plausible four-digit year (§1.3). */
const yearInput = z
  .string()
  .transform((raw) => raw.trim())
  .transform((raw) => (raw === "" ? null : raw))
  .transform((raw, ctx) => {
    if (raw === null) {
      return null;
    }

    const year = Number(raw);

    if (!/^\d{4}$/.test(raw) || year < 1885 || year > CURRENT_YEAR + 2) {
      ctx.addIssue({ code: "custom", message: "admin.identity.errors.yearInvalid" });
      return z.NEVER;
    }

    return year;
  });

// --- Trims (`variants`, ui-spec §3.1) ---------------------------------------

const VARIANTS_CAP = 20;
const VARIANT_NAME_LENGTH = 64;
const VARIANT_DESCRIPTION_LENGTH = 400;

/** Duplicated from `ModelSpecsPanel` (not exported there) — the same two pinned vocabularies. */
const PRICE_BAND_OPTIONS = [
  "budget",
  "mid",
  "upper",
  "premium",
] as const satisfies readonly NonNullable<DraftSpec["priceBand"]>[];

const CATEGORY_OPTIONS = [
  "naked",
  "sport",
  "sport_touring",
  "touring",
  "adventure",
  "cruiser",
  "classic",
  "scrambler",
  "enduro",
  "supermoto",
  "scooter",
] as const satisfies readonly NonNullable<DraftSpec["category"]>[];

/** Exactly the eight `ModelSpecsPanel` fields a trim may differ in (ui-spec §3.1 pin). */
const VARIANT_SPEC_FIELDS = [
  "engineCc",
  "powerKw",
  "torqueNm",
  "wetWeightKg",
  "seatHeightMm",
  "a2Eligible",
  "priceBand",
  "category",
] as const;

type VariantSpecField = (typeof VARIANT_SPEC_FIELDS)[number];

const VARIANT_NUMBER_UNITS = {
  engineCc: "cc",
  powerKw: "kw",
  torqueNm: "nm",
  wetWeightKg: "kg",
  seatHeightMm: "mm",
} as const;

type VariantNumberField = keyof typeof VARIANT_NUMBER_UNITS;

function isNumberSpecField(field: VariantSpecField): field is VariantNumberField {
  return field in VARIANT_NUMBER_UNITS;
}

/** The value a newly-added delta row starts from — always valid, never empty for a `Select`. */
function defaultSpecRowValue(field: VariantSpecField): string {
  if (isNumberSpecField(field)) {
    return "";
  }
  if (field === "a2Eligible") {
    return "yes";
  }
  return field === "priceBand" ? PRICE_BAND_OPTIONS[0] : CATEGORY_OPTIONS[0];
}

/** One delta row's control value → its typed `specs` entry, or an issue on `value`. */
const variantSpecRowSchema = z
  .object({
    field: z.enum([...VARIANT_SPEC_FIELDS] as [VariantSpecField, ...VariantSpecField[]]),
    value: z.string(),
  })
  .transform((row, ctx) => {
    if (isNumberSpecField(row.field)) {
      const trimmed = row.value.trim();
      const num = Number(trimmed);

      if (trimmed === "" || !Number.isFinite(num) || num <= 0) {
        ctx.addIssue({
          code: "custom",
          path: ["value"],
          message: "admin.review.specs.errors.numberInvalid",
        });
        return z.NEVER;
      }
      return { field: row.field, value: num };
    }
    if (row.field === "a2Eligible") {
      return { field: row.field, value: row.value === "yes" };
    }
    return { field: row.field, value: row.value };
  });

/** One trim card's control values → the required checks §3.1 pins (uniqueness is cross-item, below). */
const variantSchema = z
  .object({
    name: z.string(),
    description: z.string(),
    specRows: z.array(variantSpecRowSchema).max(VARIANT_SPEC_FIELDS.length),
  })
  .transform((variant, ctx) => {
    const name = variant.name.trim();

    if (name === "") {
      ctx.addIssue({
        code: "custom",
        path: ["name"],
        message: "admin.identity.variants.errors.nameRequired",
      });
    }
    if (variant.description.length > VARIANT_DESCRIPTION_LENGTH) {
      ctx.addIssue({
        code: "custom",
        path: ["description"],
        message: "admin.identity.variants.errors.descriptionTooLong",
      });
    }

    return { name, description: variant.description.trim(), specRows: variant.specRows };
  });

const identityFormSchema = z
  .object({
    // Curated by the manufacturer Autocomplete; nothing to validate beyond
    // "one of the loaded options or unselected" (the picker cannot invent one).
    manufacturer: z.custom<Manufacturer | null>(() => true),
    buildingline: trimmedNullable(64, "admin.identity.errors.buildinglineTooLong"),
    modelName: trimmedNullable(128, "admin.identity.errors.modelNameTooLong"),
    yearFrom: yearInput,
    yearTo: yearInput,
    // A safety net: entry-time handling (below) already refuses a bad-shape or
    // over-cap code before it becomes a chip, so these two checks should never
    // actually fire — kept because §1.3 pins them as part of the contract.
    typeCodes: z
      .array(z.string())
      .max(TYPE_CODES_CAP, { message: "admin.identity.errors.typeCodesMax" })
      .refine((codes) => codes.every((code) => TYPE_CODE_PATTERN.test(code)), {
        message: "admin.identity.errors.typeCodeInvalid",
      }),
    variants: z.array(variantSchema).max(VARIANTS_CAP),
  })
  .superRefine((values, ctx) => {
    if (
      values.yearFrom !== null &&
      values.yearTo !== null &&
      values.yearTo < values.yearFrom
    ) {
      ctx.addIssue({
        code: "custom",
        path: ["yearTo"],
        message: "admin.identity.errors.yearOrder",
      });
    }

    // Case-insensitive uniqueness (§3.1) — every name after the first
    // occurrence of its lower-cased spelling is flagged; an already-required
    // empty name is left to the `nameRequired` issue above.
    const seen = new Set<string>();
    values.variants.forEach((variant, index) => {
      const key = variant.name.toLowerCase();

      if (key === "") {
        return;
      }
      if (seen.has(key)) {
        ctx.addIssue({
          code: "custom",
          path: ["variants", index, "name"],
          message: "admin.identity.variants.errors.nameDuplicate",
        });
      } else {
        seen.add(key);
      }
    });
  });

type IdentityFormInput = z.input<typeof identityFormSchema>;
type IdentityFormValues = z.output<typeof identityFormSchema>;

/** The form's own fields with an inline validation/server error (`manufacturer` is not one). */
type ValidatedField = "buildingline" | "modelName" | "yearFrom" | "yearTo" | "typeCodes";

/**
 * Every §1.3 message a field can show, translated through a literal key at
 * every call site — the project's typed i18n key union (`pnpm typecheck`)
 * rejects a `t()` call whose key is a plain `string`, so a zod message or a
 * `ValidatedField` name is translated through an exhaustive `switch` instead
 * of an indexed lookup, never widened or cast.
 */
function translateIdentityErrorKey(t: TFunction, key: string): string {
  switch (key) {
    case "admin.identity.errors.modelNameTooLong":
      return t("admin.identity.errors.modelNameTooLong");
    case "admin.identity.errors.buildinglineTooLong":
      return t("admin.identity.errors.buildinglineTooLong");
    case "admin.identity.errors.yearInvalid":
      return t("admin.identity.errors.yearInvalid");
    case "admin.identity.errors.yearOrder":
      return t("admin.identity.errors.yearOrder");
    case "admin.identity.errors.typeCodeInvalid":
      return t("admin.identity.errors.typeCodeInvalid");
    case "admin.identity.errors.typeCodesMax":
      return t("admin.identity.errors.typeCodesMax");
    default:
      // Unreachable in practice — every message this form sets is one of the
      // six keys above — but a `t()` call still needs a literal key.
      return t("common.errors.serverError");
  }
}

/** The three §3.1 trim-field messages, translated the same literal-key way. */
function translateVariantFieldErrorKey(t: TFunction, key: string): string {
  switch (key) {
    case "admin.identity.variants.errors.nameRequired":
      return t("admin.identity.variants.errors.nameRequired");
    case "admin.identity.variants.errors.nameDuplicate":
      return t("admin.identity.variants.errors.nameDuplicate");
    case "admin.identity.variants.errors.descriptionTooLong":
      return t("admin.identity.variants.errors.descriptionTooLong");
    default:
      return t("common.errors.serverError");
  }
}

/**
 * A server-mapped 422 (`form.setError(field, { type: "server" })`, ui-spec
 * §1.5) carries no message of its own — the field's §1.3 message is shown
 * regardless of which specific rule the server enforced, same as a
 * client-side failure on that field.
 */
function defaultFieldErrorMessage(t: TFunction, name: ValidatedField): string {
  switch (name) {
    case "buildingline":
      return t("admin.identity.errors.buildinglineTooLong");
    case "modelName":
      return t("admin.identity.errors.modelNameTooLong");
    case "yearFrom":
    case "yearTo":
      return t("admin.identity.errors.yearInvalid");
    case "typeCodes":
      return t("admin.identity.errors.typeCodeInvalid");
  }
}

/** The identity PATCH block's attribute names → this form's field names. */
const SERVER_FIELD_TO_FORM: Record<string, keyof IdentityFormInput> = {
  manufacturerId: "manufacturer",
  buildingline: "buildingline",
  modelName: "modelName",
  yearFrom: "yearFrom",
  yearTo: "yearTo",
  typeCodes: "typeCodes",
};

function numberToInput(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

/** A stored spec value → the control's string, per field type (mirrors `defaultSpecRowValue`). */
function specValueToInput(field: VariantSpecField, value: unknown): string {
  if (isNumberSpecField(field)) {
    return String(value);
  }
  if (field === "a2Eligible") {
    return value === true ? "yes" : "no";
  }
  return String(value);
}

/** A stored trim's `specs` → the form's delta rows, in the eight fields' canonical order. */
function specRowsFromSpecs(
  specs: Record<string, unknown> | null,
): { field: VariantSpecField; value: string }[] {
  if (specs === null) {
    return [];
  }

  return VARIANT_SPEC_FIELDS.filter(
    (field) => specs[field] !== undefined && specs[field] !== null,
  ).map((field) => ({ field, value: specValueToInput(field, specs[field]) }));
}

function toFormValues(product: Product): IdentityFormInput {
  return {
    // Resolved once the manufacturer options load (see the effect below): the
    // API does not (yet) answer with a manufacturer id, only its rendered name.
    manufacturer: null,
    buildingline: product.buildingline ?? "",
    modelName: product.modelName ?? "",
    yearFrom: numberToInput(product.yearFrom),
    yearTo: numberToInput(product.yearTo),
    typeCodes: product.typeCodes ?? [],
    variants: (product.variants ?? []).map((variant) => ({
      name: variant.name,
      description: variant.description ?? "",
      specRows: specRowsFromSpecs(variant.specs),
    })),
  };
}

/**
 * The submitted form buffer's one trim → the write shape `useSaveIdentity`
 * sends. The generated `Variant` schema requires `slug`/`description`/`specs`
 * as present (non-optional) keys with empty-value defaults even though the
 * server always recomputes `slug` from `name` and ignores whatever is sent
 * (D1) — so an empty trim sends `slug: ""`, `description: ""`, `specs: {}`
 * rather than omitting them.
 */
function toVariantWrite(variant: IdentityFormValues["variants"][number]): VariantWrite {
  const specs = Object.fromEntries(variant.specRows.map((row) => [row.field, row.value]));

  return {
    slug: "",
    name: variant.name,
    description: variant.description,
    specs,
  };
}

/** One claimed year span, formatted like the CLI summary (`2019–2023`, `from 2019`). */
function formatYearRange(t: TFunction, yearFrom: number | null, yearTo: number | null): string | null {
  if (yearFrom === null && yearTo === null) {
    return null;
  }
  if (yearFrom !== null && yearTo !== null) {
    return yearFrom === yearTo
      ? t("common.modelName.yearSingle", { year: yearFrom })
      : t("common.modelName.yearRange", { from: yearFrom, to: yearTo });
  }
  return yearFrom !== null
    ? t("common.modelName.yearFrom", { from: yearFrom })
    : t("common.modelName.yearUntil", { to: yearTo });
}

/**
 * Panel-local preview of the **unsaved form buffer** — the one exception to
 * "the frontend never formats a name" (D5, adjudicated 2026-08-31: previewing
 * a value that has no server counterpart is not rendering a persisted name).
 * Not exported, not shared with any other module, and never applied to a
 * value that came back from the API — once a name is saved, the displayed
 * name is the server's rendered `name`.
 */
function previewLevels(
  t: TFunction,
  manufacturerName: string | null,
  modelNameInput: string,
  queryName: string,
  yearFrom: number | null,
  yearTo: number | null,
): { level1: string; level2: string } {
  const trimmedModel = modelNameInput.trim();
  // §11 fallback: never an empty parenthesis, never a blank name — the
  // originally-entered query name carries the preview until research fills in
  // a real model name.
  const model = trimmedModel !== "" ? trimmedModel : queryName;
  const level1 =
    manufacturerName !== null && manufacturerName !== "" ? `${manufacturerName} ${model}` : model;
  const yearRange = formatYearRange(t, yearFrom, yearTo);
  const level2 = yearRange === null ? level1 : `${level1} (${yearRange})`;

  return { level1, level2 };
}

/**
 * One delta row's value control, typed per `field` (ui-spec §3.1): a number
 * `TextField` with its unit adornment and the positive-finite rule, the
 * yes/no `Select` with **no** "unknown" option for `a2Eligible` (an absent
 * key already means "same as the base" — the risk note this step carries),
 * or the pinned `priceBand`/`category` enum `Select`.
 */
function VariantSpecValueInput({
  t,
  control,
  name,
  field,
  disabled,
  error,
}: {
  t: TFunction;
  control: Control<IdentityFormInput, unknown, IdentityFormValues>;
  name: `variants.${number}.specRows.${number}.value`;
  field: VariantSpecField;
  disabled: boolean;
  error: boolean;
}) {
  if (isNumberSpecField(field)) {
    return (
      <Controller
        control={control}
        name={name}
        render={({ field: controllerField }) => (
          <TextField
            {...controllerField}
            type="number"
            size="small"
            disabled={disabled}
            label={t("admin.identity.variants.specValue")}
            error={error}
            helperText={error ? t("admin.review.specs.errors.numberInvalid") : undefined}
            slotProps={{
              input: {
                endAdornment: (
                  <InputAdornment position="end">
                    {t(`admin.review.specs.units.${VARIANT_NUMBER_UNITS[field]}`)}
                  </InputAdornment>
                ),
              },
            }}
          />
        )}
      />
    );
  }

  if (field === "a2Eligible") {
    return (
      <Controller
        control={control}
        name={name}
        render={({ field: controllerField }) => (
          <TextField
            {...controllerField}
            select
            size="small"
            disabled={disabled}
            label={t("admin.identity.variants.specValue")}
          >
            <MenuItem value="yes">{t("common.yes")}</MenuItem>
            <MenuItem value="no">{t("common.no")}</MenuItem>
          </TextField>
        )}
      />
    );
  }

  if (field === "priceBand") {
    return (
      <Controller
        control={control}
        name={name}
        render={({ field: controllerField }) => (
          <TextField
            {...controllerField}
            select
            size="small"
            disabled={disabled}
            label={t("admin.identity.variants.specValue")}
          >
            {PRICE_BAND_OPTIONS.map((option) => (
              <MenuItem key={option} value={option}>
                {t(`common.specEnums.priceBand.${option}`, { defaultValue: option })}
              </MenuItem>
            ))}
          </TextField>
        )}
      />
    );
  }

  // `category` — the eight fields are exhaustive, but the switch above is by
  // string equality, so TS still needs this final branch spelled out.
  return (
    <Controller
      control={control}
      name={name}
      render={({ field: controllerField }) => (
        <TextField
          {...controllerField}
          select
          size="small"
          disabled={disabled}
          label={t("admin.identity.variants.specValue")}
        >
          {CATEGORY_OPTIONS.map((option) => (
            <MenuItem key={option} value={option}>
              {t(`common.specEnums.category.${option}`, { defaultValue: option })}
            </MenuItem>
          ))}
        </TextField>
      )}
    />
  );
}

/**
 * One trim card of the editor (ui-spec §3.1/display-spec §6.2): the name and
 * description fields, its own nested `useFieldArray` over `specRows`, and the
 * reorder/remove `IconButton`s the parent wires to `fieldArray.move`/`remove`.
 */
function TrimCard({
  t,
  form,
  index,
  isPending,
  isFirst,
  isLast,
  onMoveUp,
  onMoveDown,
  onRemove,
}: {
  t: TFunction;
  form: UseFormReturn<IdentityFormInput, unknown, IdentityFormValues>;
  index: number;
  isPending: boolean;
  isFirst: boolean;
  isLast: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
}) {
  const specRows = useFieldArray({
    control: form.control,
    name: `variants.${index}.specRows` as const,
  });
  const description = useWatch({ control: form.control, name: `variants.${index}.description` }) ?? "";
  const watchedRows =
    useWatch({ control: form.control, name: `variants.${index}.specRows` }) ?? [];
  const usedFields = watchedRows
    .map((row) => row?.field)
    .filter((field): field is VariantSpecField => field !== undefined);

  const variantErrors = form.formState.errors.variants?.[index];
  const nameErrorMessage = variantErrors?.name?.message;
  const descriptionErrorMessage = variantErrors?.description?.message;

  function addDifference() {
    const nextField = VARIANT_SPEC_FIELDS.find((field) => !usedFields.includes(field));

    if (nextField !== undefined) {
      specRows.append({ field: nextField, value: defaultSpecRowValue(nextField) });
    }
  }

  return (
    <ListItem disableGutters sx={{ display: "block", mb: 2 }}>
      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="flex-start" sx={{ mb: 1 }}>
            <TextField
              {...form.register(`variants.${index}.name` as const)}
              fullWidth
              size="small"
              disabled={isPending}
              label={t("admin.identity.variants.name")}
              error={nameErrorMessage !== undefined}
              helperText={
                nameErrorMessage !== undefined
                  ? translateVariantFieldErrorKey(t, nameErrorMessage)
                  : undefined
              }
              slotProps={{ htmlInput: { maxLength: VARIANT_NAME_LENGTH } }}
            />
            <IconButton
              size="small"
              disabled={isPending || isFirst}
              onClick={onMoveUp}
              aria-label={t("admin.identity.variants.moveUp")}
            >
              <Icon>arrow_upward</Icon>
            </IconButton>
            <IconButton
              size="small"
              disabled={isPending || isLast}
              onClick={onMoveDown}
              aria-label={t("admin.identity.variants.moveDown")}
            >
              <Icon>arrow_downward</Icon>
            </IconButton>
            <IconButton
              size="small"
              disabled={isPending}
              onClick={onRemove}
              aria-label={t("admin.identity.variants.remove")}
            >
              <Icon>delete</Icon>
            </IconButton>
          </Stack>
          <TextField
            {...form.register(`variants.${index}.description` as const)}
            fullWidth
            multiline
            rows={3}
            disabled={isPending}
            label={t("admin.identity.variants.description")}
            error={descriptionErrorMessage !== undefined}
            helperText={
              descriptionErrorMessage !== undefined
                ? translateVariantFieldErrorKey(t, descriptionErrorMessage)
                : t("admin.identity.variants.descriptionCount", { count: description.length })
            }
          />
          {specRows.fields.length > 0 && (
            <Stack spacing={1} sx={{ mt: 2 }}>
              {specRows.fields.map((row, rowIndex) => {
                const rowField = watchedRows[rowIndex]?.field ?? row.field;
                const options = VARIANT_SPEC_FIELDS.filter(
                  (candidate) => candidate === rowField || !usedFields.includes(candidate),
                );
                const valueErrorMessage =
                  variantErrors?.specRows?.[rowIndex]?.value?.message;

                return (
                  <Stack key={row.id} direction="row" spacing={1} alignItems="flex-start">
                    <Controller
                      control={form.control}
                      name={`variants.${index}.specRows.${rowIndex}.field` as const}
                      render={({ field: controllerField }) => (
                        <TextField
                          {...controllerField}
                          select
                          size="small"
                          sx={{ minWidth: 200 }}
                          disabled={isPending}
                          label={t("admin.identity.variants.specField")}
                          onChange={(event) => {
                            const nextField = event.target.value as VariantSpecField;

                            controllerField.onChange(nextField);
                            specRows.update(rowIndex, {
                              field: nextField,
                              value: defaultSpecRowValue(nextField),
                            });
                          }}
                        >
                          {options.map((option) => (
                            <MenuItem key={option} value={option}>
                              {t(`admin.review.specs.fields.${option}`)}
                            </MenuItem>
                          ))}
                        </TextField>
                      )}
                    />
                    <VariantSpecValueInput
                      t={t}
                      control={form.control}
                      name={`variants.${index}.specRows.${rowIndex}.value` as const}
                      field={rowField}
                      disabled={isPending}
                      error={valueErrorMessage !== undefined}
                    />
                    <IconButton
                      size="small"
                      disabled={isPending}
                      onClick={() => specRows.remove(rowIndex)}
                      aria-label={t("admin.identity.variants.removeSpec")}
                    >
                      <Icon>delete</Icon>
                    </IconButton>
                  </Stack>
                );
              })}
            </Stack>
          )}
          {specRows.fields.length < VARIANT_SPEC_FIELDS.length && (
            <Button
              size="small"
              startIcon={<Icon>add</Icon>}
              disabled={isPending}
              onClick={addDifference}
              sx={{ mt: 1 }}
            >
              {t("admin.identity.variants.addSpec")}
            </Button>
          )}
        </CardContent>
      </Card>
    </ListItem>
  );
}

/** The `admin.identity.slug` / `admin.identity.queryName` read-only context rows (§1.1). */
function ContextRows({ slug, queryName }: { slug: string; queryName: string }) {
  const { t } = useTranslation();

  return (
    <Box sx={{ mt: 2 }}>
      <Table size="small">
        <TableBody>
          <TableRow>
            <TableCell component="th" scope="row" sx={{ width: "30%" }}>
              {t("admin.identity.slug")}
            </TableCell>
            <TableCell sx={{ fontFamily: "monospace" }}>{slug}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell component="th" scope="row">
              {t("admin.identity.queryName")}
            </TableCell>
            <TableCell color="text.secondary">&quot;{queryName}&quot;</TableCell>
          </TableRow>
        </TableBody>
      </Table>
      <Typography variant="caption" color="text.secondary">
        {t("admin.identity.slugHint")}
      </Typography>
    </Box>
  );
}

/** The read-only rendering for an approved model (§1.7) — values, never a form. */
function ReadOnlyIdentity({ product }: { product: Product }) {
  const { t } = useTranslation();
  const yearRange = formatYearRange(t, product.yearFrom, product.yearTo);
  const rows: [string, string][] = [
    [t("admin.identity.manufacturer"), product.manufacturer ?? t("common.unknown")],
    [t("admin.identity.buildingline"), product.buildingline ?? t("common.unknown")],
    [t("admin.identity.modelName"), product.modelName ?? t("common.unknown")],
    [t("admin.identity.yearFrom"), yearRange ?? t("common.unknown")],
  ];

  return (
    <Box sx={{ maxWidth: 720 }}>
      {product.suggestion != null && (
        <Box sx={{ mb: 2 }}>
          <ModelClaimPanel suggestion={product.suggestion} collapsed />
        </Box>
      )}
      <Table size="small">
        <TableBody>
          {rows.map(([label, value]) => (
            <TableRow key={label}>
              <TableCell component="th" scope="row" sx={{ width: "40%" }}>
                {label}
              </TableCell>
              <TableCell>{value}</TableCell>
            </TableRow>
          ))}
          {(product.typeCodes ?? []).length > 0 && (
            <TableRow>
              <TableCell component="th" scope="row">
                {t("admin.identity.typeCodes")}
              </TableCell>
              <TableCell>
                <Stack direction="row" spacing={0.5} flexWrap="wrap">
                  {(product.typeCodes ?? []).map((code) => (
                    <Chip
                      key={code}
                      size="small"
                      variant="outlined"
                      sx={{ fontFamily: "monospace" }}
                      label={code}
                      aria-label={t("admin.identity.typeCodeA11y", { code })}
                    />
                  ))}
                </Stack>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <ContextRows slug={product.slug} queryName={product.queryName ?? product.name} />
      {(product.variants ?? []).length > 0 && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="subtitle1">{t("admin.identity.variants.heading")}</Typography>
          <Stack spacing={1} sx={{ mt: 1 }}>
            {(product.variants ?? []).map((variant) => (
              <Card key={variant.slug} variant="outlined">
                <CardContent>
                  <Typography variant="subtitle2">{variant.name}</Typography>
                  {variant.description != null && variant.description !== "" && (
                    <Typography variant="body2">{variant.description}</Typography>
                  )}
                  {variant.specs !== null && Object.keys(variant.specs).length > 0 && (
                    <Typography variant="body2" color="text.secondary">
                      {formatVariantDeltaLine(t, variant.specs)}
                    </Typography>
                  )}
                </CardContent>
              </Card>
            ))}
          </Stack>
        </Box>
      )}
    </Box>
  );
}

export function ModelIdentityPanel({
  product,
  operation,
  onDirtyChange,
}: {
  product: Product;
  /** The row's latest operation, so a succeeded-with-warnings run can be flagged (§2.4). */
  operation?: Operation;
  /**
   * Reports whether the form holds unsaved edits, so the approve dialog can warn
   * that approval publishes the last **saved** identity.
   */
  onDirtyChange: (isDirty: boolean) => void;
}) {
  const { t } = useTranslation();
  const save = useSaveIdentity(product.id);
  const manufacturers = useManufacturers();

  const [isSaved, setIsSaved] = useState(false);
  const [hasGeneralError, setHasGeneralError] = useState(false);
  const [hasDuplicateError, setHasDuplicateError] = useState(false);
  const [typeCodeInput, setTypeCodeInput] = useState("");
  const [typeCodeError, setTypeCodeError] = useState<string | null>(null);

  const form = useForm<IdentityFormInput, unknown, IdentityFormValues>({
    resolver: zodResolver(identityFormSchema),
    defaultValues: toFormValues(product),
    // Phase-1 convention: no keystroke validation anywhere.
    mode: "onSubmit",
  });

  const { errors, isDirty } = form.formState;
  const isPending = save.isPending;
  // Watches exactly the fields the live preview and the buildingline lookup
  // need — called unconditionally, above the approved-row early return below.
  // Narrower than the whole form buffer on purpose: typing a type code or a
  // buildingline must not re-render this whole panel on every keystroke, only
  // the fields the preview actually composes need to.
  const [watchedManufacturer, watchedModelName, watchedYearFrom, watchedYearTo] = useWatch({
    control: form.control,
    name: ["manufacturer", "modelName", "yearFrom", "yearTo"],
  });
  const manufacturerId = watchedManufacturer?.id ?? null;
  const buildinglines = useBuildinglines(manufacturerId);
  // Called unconditionally too, above the approved-row early return.
  const variantsArray = useFieldArray({ control: form.control, name: "variants" });

  // The dirty flag belongs to the page (the approve dialog needs it); the
  // cleanup covers unmounting too, so there is nothing left to warn about once
  // the form buffer is gone.
  useEffect(() => {
    onDirtyChange(isDirty);

    return () => {
      onDirtyChange(false);
    };
  }, [isDirty, onDirtyChange]);

  // The API does not (yet) answer with a manufacturer id, only the rendered
  // name (`product.manufacturer`) — so the initial selection is resolved by a
  // case-insensitive match against the loaded options, exactly like the claim
  // panel's own manufacturer matching. Runs once per mount; a later user edit
  // must never be clobbered by a refetch.
  const manufacturerInitialized = useRef(false);

  useEffect(() => {
    if (manufacturerInitialized.current || manufacturers.data === undefined) {
      return;
    }
    if (product.manufacturer !== null && product.manufacturer !== undefined) {
      const match = manufacturers.data.find(
        (option) => option.name.toLowerCase() === product.manufacturer?.toLowerCase(),
      );

      if (match !== undefined) {
        form.setValue("manufacturer", match);
      }
    }
    manufacturerInitialized.current = true;
  }, [manufacturers.data, product.manufacturer, form]);

  if (product.status === "approved") {
    return <ReadOnlyIdentity product={product} />;
  }

  const suggestion = product.suggestion ?? null;
  const manufacturerClaimMatch =
    suggestion !== null ? matchManufacturerClaim(suggestion, manufacturers.data ?? []) : null;
  const claimedYears = suggestion !== null ? formatClaimedYears(t, suggestion) : null;
  const collapsedYears = suggestion !== null ? collapseClaimedYears(suggestion) : null;

  const optionsError = manufacturers.isError || (manufacturerId !== null && buildinglines.isError);

  function retryOptions() {
    void manufacturers.refetch();
    if (manufacturerId !== null) {
      void buildinglines.refetch();
    }
  }

  const showResearchWarning =
    operation?.status === "succeeded" &&
    operation.message !== null &&
    operation.message !== undefined &&
    operation.message.startsWith(WARNING_SUMMARY_PREFIX);
  const warningBody = showResearchWarning
    ? (operation?.message ?? "").slice(WARNING_SUMMARY_PREFIX.length)
    : "";

  const preview = previewLevels(
    t,
    watchedManufacturer?.name ?? null,
    watchedModelName ?? "",
    product.queryName ?? product.name,
    watchedYearFrom === "" || watchedYearFrom === undefined ? null : Number(watchedYearFrom),
    watchedYearTo === "" || watchedYearTo === undefined ? null : Number(watchedYearTo),
  );

  function fieldError(name: ValidatedField): boolean {
    return errors[name] !== undefined;
  }

  function fieldErrorMessage(name: ValidatedField): string | undefined {
    if (errors[name] === undefined) {
      return undefined;
    }

    const message = errors[name]?.message;

    return typeof message === "string" && message !== ""
      ? translateIdentityErrorKey(t, message)
      : defaultFieldErrorMessage(t, name);
  }

  function handleTypeCodesChange(newValue: string[]) {
    // MUI reports the whole next array; a shrink is always a chip removal and
    // is always allowed.
    if (newValue.length <= form.getValues("typeCodes").length) {
      form.setValue("typeCodes", newValue, { shouldDirty: true });
      setTypeCodeError(null);
      return;
    }

    const current = form.getValues("typeCodes");
    const candidate = newValue[newValue.length - 1] ?? "";
    const normalized = candidate.trim().toUpperCase();

    if (current.length >= TYPE_CODES_CAP) {
      setTypeCodeError("admin.identity.errors.typeCodesMax");
      return;
    }
    if (!TYPE_CODE_PATTERN.test(normalized)) {
      setTypeCodeError("admin.identity.errors.typeCodeInvalid");
      return;
    }

    setTypeCodeInput("");
    setTypeCodeError(null);
    // Duplicates are dropped silently rather than added twice.
    if (!current.includes(normalized)) {
      form.setValue("typeCodes", [...current, normalized], { shouldDirty: true });
    }
  }

  const submit = form.handleSubmit((formValues) => {
    setHasGeneralError(false);
    setHasDuplicateError(false);

    save.mutate(
      {
        values: {
          manufacturerId: formValues.manufacturer?.id ?? null,
          buildingline: formValues.buildingline,
          modelName: formValues.modelName,
          yearFrom: formValues.yearFrom,
          yearTo: formValues.yearTo,
          typeCodes: formValues.typeCodes,
          variants: formValues.variants.map(toVariantWrite),
        },
      },
      {
        onSuccess: () => {
          // Reset to what was just sent: the form is no longer dirty, and the
          // refetched row carries the same values plus the recomputed slug.
          form.reset(form.getValues());
          setIsSaved(true);
        },
        onError: (error) => {
          if (!(error instanceof SaveIdentityError)) {
            setHasGeneralError(true);
            return;
          }

          if (error.status === 409 || error.code === "duplicate-model") {
            setHasDuplicateError(true);
            return;
          }

          const mappable = error.validationFields
            .map((field) => SERVER_FIELD_TO_FORM[field])
            .filter((field): field is keyof IdentityFormInput => field !== undefined);

          for (const field of mappable) {
            form.setError(field, { type: "server" });
          }

          if (mappable.length === 0) {
            setHasGeneralError(true);
          }
        },
      },
    );
  });

  return (
    <Box component="form" noValidate onSubmit={submit} sx={{ maxWidth: 900 }}>
      {suggestion !== null && <ModelClaimPanel suggestion={suggestion} />}
      {showResearchWarning && (
        <Alert severity="warning" icon={<Icon>report</Icon>} sx={{ mb: 2 }}>
          <Typography variant="subtitle2">{t("admin.identity.researchWarnings")}</Typography>
          <Typography variant="body2">{warningBody}</Typography>
        </Alert>
      )}
      {optionsError && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button size="small" onClick={retryOptions}>
              {t("common.retry")}
            </Button>
          }
        >
          {t("admin.identity.optionsLoadError")}
        </Alert>
      )}
      {hasDuplicateError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {t("admin.identity.errors.duplicateIdentity")}
        </Alert>
      )}
      {hasGeneralError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {t("common.errors.serverError")}
        </Alert>
      )}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6 }}>
          {manufacturers.isPending ? (
            <Skeleton variant="rounded" height={56} />
          ) : (
            <Controller
              name="manufacturer"
              control={form.control}
              render={({ field }) => (
                <Autocomplete
                  options={manufacturers.data ?? []}
                  getOptionLabel={(option) => option.name}
                  isOptionEqualToValue={(option, value) => option.id === value.id}
                  value={field.value}
                  disabled={isPending}
                  onChange={(_event, newValue) => field.onChange(newValue)}
                  renderInput={(params) => (
                    <TextField {...params} label={t("admin.identity.manufacturer")} />
                  )}
                />
              )}
            />
          )}
          {suggestion?.manufacturer != null && (
            <ClaimFieldRow
              value={suggestion.manufacturer}
              useLabel={t("admin.identity.claim.use")}
              useA11yLabel={t("admin.identity.claim.useA11y", {
                field: t("admin.identity.manufacturer"),
              })}
              disabled={isPending}
              onUse={
                manufacturerClaimMatch !== null
                  ? () => form.setValue("manufacturer", manufacturerClaimMatch, { shouldDirty: true })
                  : undefined
              }
              noMatchCaption={
                manufacturerClaimMatch === null
                  ? t("admin.identity.claim.noManufacturerMatch")
                  : undefined
              }
            />
          )}
        </Grid>
        <Grid size={{ xs: 12, sm: 6 }}>
          {manufacturerId === null ? (
            <TextField
              fullWidth
              disabled
              label={t("admin.identity.buildingline")}
              helperText={t("admin.identity.buildinglineNeedsManufacturer")}
            />
          ) : buildinglines.isPending ? (
            <Skeleton variant="rounded" height={56} />
          ) : (
            <Controller
              name="buildingline"
              control={form.control}
              render={({ field }) => (
                <Autocomplete
                  freeSolo
                  options={buildinglines.data ?? []}
                  disabled={isPending}
                  value={field.value}
                  inputValue={field.value}
                  onChange={(_event, newValue) => field.onChange(newValue ?? "")}
                  onInputChange={(_event, newInputValue, reason) => {
                    if (reason === "input") {
                      field.onChange(newInputValue);
                    }
                  }}
                  onBlur={() => {
                    const match = (buildinglines.data ?? []).find(
                      (option) => option.toLowerCase() === field.value.trim().toLowerCase(),
                    );

                    if (match !== undefined && match !== field.value) {
                      field.onChange(match);
                    }
                    field.onBlur();
                  }}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label={t("admin.identity.buildingline")}
                      error={fieldError("buildingline")}
                      helperText={fieldErrorMessage("buildingline") ?? t("admin.identity.buildinglineHint")}
                    />
                  )}
                />
              )}
            />
          )}
        </Grid>
        <Grid size={{ xs: 12 }}>
          <TextField
            {...form.register("modelName")}
            fullWidth
            disabled={isPending}
            label={t("admin.identity.modelName")}
            error={fieldError("modelName")}
            helperText={fieldErrorMessage("modelName") ?? t("admin.identity.modelNameHint")}
          />
          {suggestion?.model != null && (
            <ClaimFieldRow
              value={suggestion.model}
              useLabel={t("admin.identity.claim.use")}
              useA11yLabel={t("admin.identity.claim.useA11y", {
                field: t("admin.identity.modelName"),
              })}
              disabled={isPending}
              onUse={() =>
                form.setValue("modelName", suggestion.model ?? "", { shouldDirty: true })
              }
            />
          )}
        </Grid>
        <Grid size={{ xs: 12, sm: 6 }}>
          <TextField
            {...form.register("yearFrom")}
            fullWidth
            disabled={isPending}
            label={t("admin.identity.yearFrom")}
            error={fieldError("yearFrom")}
            helperText={fieldErrorMessage("yearFrom")}
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6 }}>
          <TextField
            {...form.register("yearTo")}
            fullWidth
            disabled={isPending}
            label={t("admin.identity.yearTo")}
            error={fieldError("yearTo")}
            helperText={fieldErrorMessage("yearTo") ?? t("admin.identity.yearToHint")}
          />
          {claimedYears !== null && (
            <ClaimFieldRow
              value={claimedYears}
              useLabel={t("admin.identity.claim.use")}
              useA11yLabel={t("admin.identity.claim.useA11y", {
                field: `${t("admin.identity.yearFrom")}/${t("admin.identity.yearTo")}`,
              })}
              disabled={isPending}
              onUse={
                collapsedYears !== null
                  ? () => {
                      form.setValue("yearFrom", String(collapsedYears.yearFrom), {
                        shouldDirty: true,
                      });
                      form.setValue(
                        "yearTo",
                        collapsedYears.yearTo === null ? "" : String(collapsedYears.yearTo),
                        { shouldDirty: true },
                      );
                    }
                  : undefined
              }
            />
          )}
        </Grid>
        <Grid size={{ xs: 12 }}>
          <Controller
            name="typeCodes"
            control={form.control}
            render={({ field }) => (
              <Autocomplete
                multiple
                freeSolo
                options={[]}
                disabled={isPending}
                value={field.value}
                inputValue={typeCodeInput}
                onInputChange={(_event, newInputValue, reason) => {
                  if (reason === "input") {
                    setTypeCodeInput(newInputValue);
                    setTypeCodeError(null);
                  }
                }}
                onChange={(_event, newValue) => handleTypeCodesChange(newValue as string[])}
                renderTags={(tagValue, getTagProps) =>
                  tagValue.map((code, index) => (
                    <Chip
                      {...getTagProps({ index })}
                      key={code}
                      size="small"
                      label={code}
                      sx={{ fontFamily: "monospace" }}
                      aria-label={t("admin.identity.typeCodeA11y", { code })}
                    />
                  ))
                }
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label={t("admin.identity.typeCodes")}
                    error={typeCodeError !== null || fieldError("typeCodes")}
                    helperText={
                      typeCodeError !== null
                        ? translateIdentityErrorKey(t, typeCodeError)
                        : (fieldErrorMessage("typeCodes") ?? t("admin.identity.typeCodesHint"))
                    }
                  />
                )}
              />
            )}
          />
          {suggestion !== null && suggestion.typeCodes.length > 0 && (
            <ClaimFieldRow
              value={formatClaimedTypeCodes(suggestion)}
              useLabel={t("admin.identity.claim.use")}
              useA11yLabel={t("admin.identity.claim.useA11y", {
                field: t("admin.identity.typeCodes"),
              })}
              disabled={isPending}
              onUse={() => {
                const { codes, capped } = unionTypeCodes(
                  form.getValues("typeCodes"),
                  suggestion.typeCodes,
                );

                form.setValue("typeCodes", codes, { shouldDirty: true });
                setTypeCodeError(capped ? "admin.identity.errors.typeCodesMax" : null);
              }}
            />
          )}
        </Grid>
      </Grid>

      <ContextRows slug={product.slug} queryName={product.queryName ?? product.name} />

      <Box sx={{ mt: 3 }}>
        <Typography variant="subtitle1">{t("admin.identity.variants.heading")}</Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {t("admin.identity.variants.baseHint")}
        </Typography>
        {variantsArray.fields.length === 0 ? (
          // Empty state is normal copy, never an error (§3.1 pin) — no
          // `EmptyState` component, no warning colour.
          <Typography variant="body2" color="text.secondary">
            {t("admin.identity.variants.empty")}
          </Typography>
        ) : (
          <List disablePadding>
            {variantsArray.fields.map((field, index) => (
              <TrimCard
                key={field.id}
                t={t}
                form={form}
                index={index}
                isPending={isPending}
                isFirst={index === 0}
                isLast={index === variantsArray.fields.length - 1}
                onMoveUp={() => variantsArray.move(index, index - 1)}
                onMoveDown={() => variantsArray.move(index, index + 1)}
                onRemove={() => variantsArray.remove(index)}
              />
            ))}
          </List>
        )}
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
          <Button
            size="small"
            startIcon={<Icon>add</Icon>}
            disabled={isPending || variantsArray.fields.length >= VARIANTS_CAP}
            onClick={() => variantsArray.append({ name: "", description: "", specRows: [] })}
          >
            {t("admin.identity.variants.add")}
          </Button>
          {variantsArray.fields.length >= VARIANTS_CAP && (
            <Typography variant="caption" color="text.secondary">
              {t("admin.identity.variants.errors.max")}
            </Typography>
          )}
        </Stack>
      </Box>

      <Box sx={{ mt: 3 }}>
        <Typography variant="subtitle2">{t("admin.identity.preview.heading")}</Typography>
        <Typography variant="body2">
          {t("admin.identity.preview.level", { n: 1 })}: {preview.level1}
        </Typography>
        <Typography variant="body2">
          {t("admin.identity.preview.level", { n: 2 })}: {preview.level2}
        </Typography>
      </Box>

      <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
        <Button
          type="submit"
          variant="contained"
          disabled={!isDirty || isPending}
          startIcon={
            isPending ? <CircularProgress size={20} color="inherit" /> : undefined
          }
        >
          {t("admin.identity.save")}
        </Button>
        <Button disabled={!isDirty || isPending} onClick={() => form.reset()}>
          {t("admin.identity.discard")}
        </Button>
      </Stack>
      <Snackbar
        open={isSaved}
        autoHideDuration={4000}
        onClose={() => setIsSaved(false)}
      >
        <Alert severity="success">{t("admin.identity.saved")}</Alert>
      </Snackbar>
    </Box>
  );
}
