import { zodResolver } from "@hookform/resolvers/zod";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Grid from "@mui/material/Grid";
import InputAdornment from "@mui/material/InputAdornment";
import MenuItem from "@mui/material/MenuItem";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";
import { Controller, useForm, type Path } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

import {
  SaveDraftSpecError,
  useSaveDraftSpec,
  type DraftSpec,
} from "../hooks/useProductReview";
import type { Product } from "../hooks/useProducts";

/**
 * The Specs tab: the draft specification as an editable form, or — once the
 * model is published — the verified specification as a read-only table.
 *
 * Binding rule: admins edit the **draft** only. Approving the model is what
 * promotes those values to the verified specification, and no path in this UI
 * ever writes a verified row.
 *
 * This is the phase's only React-Hook-Form + Zod form (permitted by the stack
 * doc for exactly this case: sixteen frozen spec fields, three-state nullables
 * and unit-carrying numbers outgrew the plain controlled inputs used elsewhere).
 * Validation runs on submit only, like every other form in this application.
 */

/** The two pinned spec vocabularies, checked against the generated API enums. */
type PriceBand = NonNullable<DraftSpec["priceBand"]>;
type SpecCategory = NonNullable<DraftSpec["category"]>;

const PRICE_BAND_OPTIONS = [
  "budget",
  "mid",
  "upper",
  "premium",
] as const satisfies readonly PriceBand[];

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
] as const satisfies readonly SpecCategory[];

/** The numeric fields of the form, each with the unit shown as an adornment. */
const NUMBER_FIELDS = [
  { name: "engineCc", unit: "cc" },
  { name: "powerKw", unit: "kw" },
  { name: "torqueNm", unit: "nm" },
  { name: "wetWeightKg", unit: "kg" },
  { name: "seatHeightMm", unit: "mm" },
] as const;

/**
 * A number the extraction may not have found: the input carries a string, an
 * empty one means "still unknown" (the extraction contract is "leave unknown
 * fields null", and null is a legitimate saved value), anything else must be a
 * positive finite number — no weights of -12 kg.
 */
const numberInput = z
  .string()
  .transform((raw) => raw.trim())
  .transform((raw) => (raw === "" ? null : Number(raw)))
  .refine((value) => value === null || (Number.isFinite(value) && value > 0));

const specFormSchema = z.object({
  engineCc: numberInput,
  powerKw: numberInput,
  torqueNm: numberInput,
  wetWeightKg: numberInput,
  seatHeightMm: numberInput,
  // Three states, not a checkbox: a checkbox cannot say "the extractor did not
  // know", and that null is what the Phase-3 licence-check tool reads.
  a2Eligible: z
    .enum(["unknown", "yes", "no"])
    .transform((value) => (value === "unknown" ? null : value === "yes")),
  priceBand: z
    .enum(["", ...PRICE_BAND_OPTIONS])
    .transform((value) => (value === "" ? null : value)),
  category: z
    .enum(["", ...CATEGORY_OPTIONS])
    .transform((value) => (value === "" ? null : value)),
});

/** What the controls hold (strings) versus what a valid submit yields. */
type SpecFormInput = z.input<typeof specFormSchema>;
type SpecFormValues = z.output<typeof specFormSchema>;

const FORM_FIELDS = [
  "engineCc",
  "powerKw",
  "torqueNm",
  "wetWeightKg",
  "seatHeightMm",
  "a2Eligible",
  "priceBand",
  "category",
] as const satisfies readonly Path<SpecFormInput>[];

function isFormField(name: string): name is (typeof FORM_FIELDS)[number] {
  return (FORM_FIELDS as readonly string[]).includes(name);
}

function numberToInput(value: number | null): string {
  return value === null ? "" : String(value);
}

/** Server shape → control shape; a missing draft simply starts out all-unknown. */
function toFormValues(spec: DraftSpec | null): SpecFormInput {
  return {
    engineCc: numberToInput(spec?.engineCc ?? null),
    powerKw: numberToInput(spec?.powerKw ?? null),
    torqueNm: numberToInput(spec?.torqueNm ?? null),
    wetWeightKg: numberToInput(spec?.wetWeightKg ?? null),
    seatHeightMm: numberToInput(spec?.seatHeightMm ?? null),
    a2Eligible:
      spec?.a2Eligible === null || spec?.a2Eligible === undefined
        ? "unknown"
        : spec.a2Eligible
          ? "yes"
          : "no",
    priceBand: spec?.priceBand ?? "",
    category: spec?.category ?? "",
  };
}

/**
 * The read-only rendering of a specification, used for the verified spec of a
 * published model — same fields as the form, values with their units.
 */
function SpecValueTable({ spec }: { spec: DraftSpec | null }) {
  const { t } = useTranslation();
  const unknown = t("common.unknown");

  function numberRow(field: (typeof NUMBER_FIELDS)[number]): string {
    const value = spec?.[field.name] ?? null;

    return value === null
      ? unknown
      : `${value} ${t(`admin.review.specs.units.${field.unit}`)}`;
  }

  const a2Eligible = spec?.a2Eligible ?? null;
  const rows: [string, string][] = [
    ...NUMBER_FIELDS.map(
      (field): [string, string] => [
        t(`admin.review.specs.fields.${field.name}`),
        numberRow(field),
      ],
    ),
    [
      t("admin.review.specs.fields.a2Eligible"),
      a2Eligible === null ? unknown : t(a2Eligible ? "common.yes" : "common.no"),
    ],
    [
      t("admin.review.specs.fields.priceBand"),
      spec?.priceBand === null || spec?.priceBand === undefined
        ? unknown
        : t(`common.specEnums.priceBand.${spec.priceBand}`, {
            defaultValue: spec.priceBand,
          }),
    ],
    [
      t("admin.review.specs.fields.category"),
      spec?.category === null || spec?.category === undefined
        ? unknown
        : t(`common.specEnums.category.${spec.category}`, {
            defaultValue: spec.category,
          }),
    ],
  ];

  return (
    <Table size="small">
      <TableBody>
        {rows.map(([label, value]) => (
          <TableRow key={label}>
            <TableCell component="th" scope="row" sx={{ width: "50%" }}>
              {label}
            </TableCell>
            <TableCell>{value}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/**
 * The `extra` long tail: whatever the extraction found beyond the frozen
 * columns. Read-only in this phase (it is never filtered on), and omitted
 * entirely when there is nothing in it.
 */
function ExtraTable({ extra }: { extra: DraftSpec["extra"] | undefined }) {
  const { t } = useTranslation();
  const entries = Object.entries(extra ?? {});

  if (entries.length === 0) {
    return null;
  }

  return (
    <>
      <Typography variant="subtitle1" sx={{ mt: 3 }}>
        {t("admin.review.specs.extraHeading")}
      </Typography>
      <Table size="small">
        <TableBody>
          {entries.map(([key, value]) => (
            <TableRow key={key}>
              <TableCell component="th" scope="row" sx={{ width: "50%" }}>
                {key}
              </TableCell>
              <TableCell>
                {typeof value === "string" ? value : JSON.stringify(value)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </>
  );
}

export function ModelSpecsPanel({
  product,
  onDirtyChange,
}: {
  product: Product;
  /**
   * Reports whether the form holds unsaved edits, so the approve dialog can warn
   * that approval publishes the last **saved** draft.
   */
  onDirtyChange: (isDirty: boolean) => void;
}) {
  const { t } = useTranslation();
  const save = useSaveDraftSpec(product.id);
  const [isSaved, setIsSaved] = useState(false);
  const [hasGeneralError, setHasGeneralError] = useState(false);

  const form = useForm<SpecFormInput, unknown, SpecFormValues>({
    resolver: zodResolver(specFormSchema),
    defaultValues: toFormValues(product.draftSpec),
    // Phase-1 convention: no keystroke validation anywhere.
    mode: "onSubmit",
  });

  const { errors, isDirty } = form.formState;
  const isPending = save.isPending;

  // The dirty flag belongs to the page (the approve dialog needs it), while the
  // form buffer belongs here. The cleanup also covers unmounting: with the
  // buffer gone there are no unsaved edits left to warn about.
  useEffect(() => {
    onDirtyChange(isDirty);

    return () => {
      onDirtyChange(false);
    };
  }, [isDirty, onDirtyChange]);

  // A published model shows what is published: the verified values, read-only.
  if (product.status === "approved") {
    return (
      <Box sx={{ maxWidth: 720 }}>
        <Typography variant="h6" component="h3" gutterBottom>
          {t("admin.review.specs.verifiedHeading")}
        </Typography>
        <SpecValueTable spec={product.verifiedSpec} />
        <ExtraTable extra={product.verifiedSpec?.extra} />
      </Box>
    );
  }

  const submit = form.handleSubmit((values) => {
    setHasGeneralError(false);

    save.mutate(
      { values },
      {
        onSuccess: () => {
          // Reset to what was just sent: the form is no longer dirty, and the
          // refetched draft carries the same values.
          form.reset(form.getValues());
          setIsSaved(true);
        },
        onError: (error) => {
          const fields =
            error instanceof SaveDraftSpecError ? error.validationFields : [];
          const mappable = fields.filter(isFormField);

          for (const field of mappable) {
            form.setError(field, { type: "server" });
          }

          // Nothing to pin the failure on (network, 5xx, an unmappable 422):
          // say so above the form and keep every typed value.
          if (mappable.length === 0) {
            setHasGeneralError(true);
          }
        },
      },
    );
  });

  function fieldError(name: (typeof FORM_FIELDS)[number]): boolean {
    return errors[name] !== undefined;
  }

  return (
    <Box component="form" noValidate onSubmit={submit} sx={{ maxWidth: 900 }}>
      <Typography variant="h6" component="h3">
        {t("admin.review.specs.draftHeading")}
      </Typography>
      <Typography variant="body2" color="text.secondary" gutterBottom>
        {t("admin.review.specs.draftHint")}
      </Typography>
      {hasGeneralError && (
        <Alert severity="error" sx={{ my: 2 }}>
          {t("common.errors.serverError")}
        </Alert>
      )}
      <Grid container spacing={2} sx={{ mt: 1 }}>
        {NUMBER_FIELDS.map((field) => (
          <Grid key={field.name} size={{ xs: 12, sm: 6 }}>
            <TextField
              {...form.register(field.name)}
              type="number"
              fullWidth
              disabled={isPending}
              label={t(`admin.review.specs.fields.${field.name}`)}
              error={fieldError(field.name)}
              helperText={
                fieldError(field.name)
                  ? t("admin.review.specs.errors.numberInvalid")
                  : undefined
              }
              slotProps={{
                input: {
                  endAdornment: (
                    <InputAdornment position="end">
                      {t(`admin.review.specs.units.${field.unit}`)}
                    </InputAdornment>
                  ),
                },
              }}
            />
          </Grid>
        ))}
        <Grid size={{ xs: 12, sm: 6 }}>
          <Controller
            name="a2Eligible"
            control={form.control}
            render={({ field }) => (
              <TextField
                {...field}
                select
                fullWidth
                disabled={isPending}
                label={t("admin.review.specs.fields.a2Eligible")}
              >
                <MenuItem value="unknown">{t("common.unknown")}</MenuItem>
                <MenuItem value="yes">{t("common.yes")}</MenuItem>
                <MenuItem value="no">{t("common.no")}</MenuItem>
              </TextField>
            )}
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6 }}>
          <Controller
            name="priceBand"
            control={form.control}
            render={({ field }) => (
              <TextField
                {...field}
                select
                fullWidth
                disabled={isPending}
                label={t("admin.review.specs.fields.priceBand")}
              >
                <MenuItem value="">{t("common.unknown")}</MenuItem>
                {PRICE_BAND_OPTIONS.map((value) => (
                  <MenuItem key={value} value={value}>
                    {t(`common.specEnums.priceBand.${value}`, {
                      defaultValue: value,
                    })}
                  </MenuItem>
                ))}
              </TextField>
            )}
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6 }}>
          <Controller
            name="category"
            control={form.control}
            render={({ field }) => (
              <TextField
                {...field}
                select
                fullWidth
                disabled={isPending}
                label={t("admin.review.specs.fields.category")}
              >
                <MenuItem value="">{t("common.unknown")}</MenuItem>
                {CATEGORY_OPTIONS.map((value) => (
                  <MenuItem key={value} value={value}>
                    {t(`common.specEnums.category.${value}`, {
                      defaultValue: value,
                    })}
                  </MenuItem>
                ))}
              </TextField>
            )}
          />
        </Grid>
      </Grid>
      <ExtraTable extra={product.draftSpec?.extra} />
      <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
        <Button
          type="submit"
          variant="contained"
          disabled={!isDirty || isPending}
          startIcon={
            isPending ? <CircularProgress size={20} color="inherit" /> : undefined
          }
        >
          {t("admin.review.specs.save")}
        </Button>
        <Button disabled={!isDirty || isPending} onClick={() => form.reset()}>
          {t("admin.review.specs.resetBtn")}
        </Button>
      </Stack>
      <Snackbar
        open={isSaved}
        autoHideDuration={4000}
        onClose={() => setIsSaved(false)}
      >
        <Alert severity="success">{t("admin.review.specs.saved")}</Alert>
      </Snackbar>
    </Box>
  );
}
