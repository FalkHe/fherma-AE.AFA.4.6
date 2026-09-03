import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Icon from "@mui/material/Icon";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import type { KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";

import {
  PRICE_BAND_VALUES,
  SPEC_CATEGORY_VALUES,
  useCatalogueFilters,
  type PriceBand,
  type SpecCategory,
} from "../hooks/useCatalogueFilters";
import { useManufacturers } from "../hooks/useCatalogueModels";

import { formatSpecEnum } from "./specFields";

/**
 * The catalogue filter stack (ui-spec §3.4), rendered in the desktop sidebar and
 * inside the mobile drawer — one component, one behaviour.
 *
 * Every control reads from and writes to the URL through `useCatalogueFilters`;
 * **no control keeps a copy of its value in React state.** A second copy would
 * be a second truth, and the URL is the one that survives a reload, a shared
 * link and the back button.
 *
 * Apply behaviour: selects and the checkbox apply on change (one discrete
 * intent, one refetch), number fields on blur or Enter. Typing does not touch
 * the URL — that is the only reason the number fields are uncontrolled, and the
 * `key` remount is what re-syncs them when the URL changes from outside (clear
 * filters, back button).
 */

/** Off-screen but in the accessibility tree — the fieldset's legend. */
const visuallyHidden = {
  position: "absolute",
  width: 1,
  height: 1,
  p: 0,
  m: -1,
  overflow: "hidden",
  clip: "rect(0 0 0 0)",
  whiteSpace: "nowrap",
  border: 0,
} as const;

/**
 * A number filter: uncontrolled while typing, committed on blur or Enter. An
 * empty or invalid commit removes the param — "no bound" is a legitimate value,
 * and a half-typed number is not an intent.
 */
function NumberFilterField({
  label,
  value,
  onCommit,
}: {
  label: string;
  value: number | null;
  onCommit: (value: number | null) => void;
}) {
  function commit(input: HTMLInputElement) {
    const raw = input.value.trim();
    const parsed = Number(raw);

    onCommit(raw === "" || !Number.isFinite(parsed) || parsed <= 0 ? null : parsed);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    // `isComposing`: an IME's Enter confirms a candidate, it does not submit.
    if (event.key === "Enter" && !event.nativeEvent.isComposing) {
      event.preventDefault();
      commit(event.target as HTMLInputElement);
    }
  }

  return (
    <TextField
      // Remounts whenever the URL value changes from outside this field, so the
      // uncontrolled buffer can never drift from the shareable state.
      key={String(value ?? "")}
      type="number"
      size="small"
      fullWidth
      label={label}
      defaultValue={value ?? ""}
      slotProps={{ htmlInput: { min: 0, inputMode: "numeric" } }}
      onBlur={(event) => commit(event.target as HTMLInputElement)}
      onKeyDown={handleKeyDown}
    />
  );
}

export function CatalogueFilters() {
  const { t } = useTranslation();
  const { filters, setFilter, clearFilters, activeFilterCount } = useCatalogueFilters();
  const manufacturers = useManufacturers();

  /** MUI types a multiple `Select`'s value as `string`; it is an array here. */
  function selectedMembers(value: string): string[] {
    return typeof value === "string" ? value.split(",") : (value as unknown as string[]);
  }

  return (
    <Stack spacing={2} component="fieldset" sx={{ border: 0, m: 0, p: 0 }}>
      <Box component="legend" sx={visuallyHidden}>
        {t("catalogue.filters.title")}
      </Box>

      <TextField
        select
        size="small"
        fullWidth
        label={t("catalogue.filters.category")}
        value={filters.category}
        onChange={(event) => {
          const members = selectedMembers(event.target.value);

          setFilter({
            category: SPEC_CATEGORY_VALUES.filter((value) => members.includes(value)),
          });
        }}
        slotProps={{
          select: {
            multiple: true,
            renderValue: (selected) =>
              (selected as SpecCategory[])
                .map((value) => formatSpecEnum(t, "category", value))
                .join(", "),
          },
        }}
      >
        {SPEC_CATEGORY_VALUES.map((value) => (
          <MenuItem key={value} value={value}>
            <Checkbox size="small" checked={filters.category.includes(value)} />
            <ListItemText primary={formatSpecEnum(t, "category", value)} />
          </MenuItem>
        ))}
      </TextField>

      <TextField
        select
        size="small"
        fullWidth
        label={t("catalogue.filters.priceBand")}
        value={filters.priceBand}
        onChange={(event) => {
          const members = selectedMembers(event.target.value);

          setFilter({
            priceBand: PRICE_BAND_VALUES.filter((value) => members.includes(value)),
          });
        }}
        slotProps={{
          select: {
            multiple: true,
            renderValue: (selected) =>
              (selected as PriceBand[])
                .map((value) => formatSpecEnum(t, "priceBand", value))
                .join(", "),
          },
        }}
      >
        {PRICE_BAND_VALUES.map((value) => (
          <MenuItem key={value} value={value}>
            <Checkbox size="small" checked={filters.priceBand.includes(value)} />
            <ListItemText primary={formatSpecEnum(t, "priceBand", value)} />
          </MenuItem>
        ))}
      </TextField>

      <TextField
        select
        size="small"
        fullWidth
        // The options are a non-critical lookup: while they are missing the
        // select is simply unavailable, and the other filters keep working.
        disabled={manufacturers.data === undefined}
        label={t("catalogue.filters.manufacturer")}
        value={filters.manufacturer ?? ""}
        onChange={(event) => setFilter({ manufacturer: event.target.value })}
      >
        <MenuItem value="">{t("catalogue.filters.manufacturerAll")}</MenuItem>
        {(manufacturers.data ?? []).map((manufacturer) => (
          <MenuItem key={manufacturer.id} value={manufacturer.id}>
            {manufacturer.name}
          </MenuItem>
        ))}
      </TextField>

      <Box>
        <Typography variant="caption" color="text.secondary">
          {t("catalogue.filters.engineCc")}
        </Typography>
        <Stack direction="row" spacing={1}>
          <NumberFilterField
            label={t("catalogue.filters.min")}
            value={filters.ccMin}
            onCommit={(value) => setFilter({ ccMin: value })}
          />
          <NumberFilterField
            label={t("catalogue.filters.max")}
            value={filters.ccMax}
            onCommit={(value) => setFilter({ ccMax: value })}
          />
        </Stack>
      </Box>

      <Box>
        <Typography variant="caption" color="text.secondary">
          {t("catalogue.filters.powerKw")}
        </Typography>
        <Stack direction="row" spacing={1}>
          <NumberFilterField
            label={t("catalogue.filters.min")}
            value={filters.kwMin}
            onCommit={(value) => setFilter({ kwMin: value })}
          />
          <NumberFilterField
            label={t("catalogue.filters.max")}
            value={filters.kwMax}
            onCommit={(value) => setFilter({ kwMax: value })}
          />
        </Stack>
      </Box>

      <NumberFilterField
        label={t("catalogue.filters.seatHeightMax")}
        value={filters.seatMax}
        onCommit={(value) => setFilter({ seatMax: value })}
      />
      <NumberFilterField
        label={t("catalogue.filters.weightMax")}
        value={filters.weightMax}
        onCommit={(value) => setFilter({ weightMax: value })}
      />

      <FormControlLabel
        control={
          <Checkbox
            checked={filters.a2}
            onChange={(event) => setFilter({ a2: event.target.checked })}
          />
        }
        label={t("catalogue.filters.a2Only")}
      />

      <Button
        variant="text"
        startIcon={<Icon>filter_alt_off</Icon>}
        disabled={activeFilterCount === 0}
        onClick={clearFilters}
      >
        {t("catalogue.list.clearFilters")}
      </Button>
    </Stack>
  );
}
