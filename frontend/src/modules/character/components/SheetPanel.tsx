// The live "your sheet so far" panel (sprint 009-06, WI1, AC3, research.md
// Decision 6): one field list, rendered once, wrapped in whichever frame the
// caller picked via `collapsed` — a side panel on a wide screen, or an
// Accordion whose closed summary is the narrow-screen strip. `collapsed` is
// a plain prop, not a `useMediaQuery` call in here, so this component stays
// trivially testable at both sizes without depending on the test suite's
// `matchMedia` stub (frontend-stack.md "Test arrangement"; research.md
// facts).
import type { ReactElement } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { SheetSoFar } from "../hooks/useCreationChat";

export interface SheetPanelProps {
  sheet: SheetSoFar | null;
  stepNumber: number;
  collapsed: boolean;
}

interface FieldRow {
  label: string;
  value: string;
}

function formatList(values: string[] | undefined, empty: string): string {
  return values && values.length > 0 ? values.join(", ") : empty;
}

export function SheetPanel({ sheet, stepNumber, collapsed }: SheetPanelProps): ReactElement {
  const { t } = useTranslation("character");
  const empty = t("sheet.empty");

  const abilities = sheet?.abilities ?? null;
  const rows: FieldRow[] = [
    { label: t("sheet.fields.name"), value: sheet?.name ?? empty },
    { label: t("sheet.fields.race"), value: sheet?.race ?? empty },
    { label: t("sheet.fields.class"), value: sheet?.characterClass ?? empty },
    { label: t("sheet.fields.level"), value: sheet?.level != null ? String(sheet.level) : empty },
    { label: t("sheet.fields.alignment"), value: sheet?.alignment ?? empty },
    { label: t("sheet.fields.abilities.str"), value: abilities ? String(abilities.strength) : empty },
    { label: t("sheet.fields.abilities.dex"), value: abilities ? String(abilities.dexterity) : empty },
    { label: t("sheet.fields.abilities.con"), value: abilities ? String(abilities.constitution) : empty },
    { label: t("sheet.fields.abilities.int"), value: abilities ? String(abilities.intelligence) : empty },
    { label: t("sheet.fields.abilities.wis"), value: abilities ? String(abilities.wisdom) : empty },
    { label: t("sheet.fields.abilities.cha"), value: abilities ? String(abilities.charisma) : empty },
    { label: t("sheet.fields.hitPoints"), value: sheet?.maxHp != null ? String(sheet.maxHp) : empty },
    { label: t("sheet.fields.armourClass"), value: sheet?.armourClass != null ? String(sheet.armourClass) : empty },
    { label: t("sheet.fields.skills"), value: formatList(sheet?.skills, empty) },
    { label: t("sheet.fields.equipment"), value: formatList(sheet?.equipment, empty) },
  ];

  const raceClass = [sheet?.race, sheet?.characterClass].filter(Boolean).join(" ") || empty;
  const level = sheet?.level != null ? String(sheet.level) : empty;
  const stripLabel = t("sheet.strip", { raceClass, level, n: stepNumber });

  const fieldList = (
    <Stack spacing={2} component="dl" sx={{ m: 0 }}>
      <Typography variant="overline" sx={{ color: "text.secondary" }}>
        {t("sheet.heading")}
      </Typography>
      {rows.map((row) => (
        <Stack key={row.label} direction="row" spacing={2} sx={{ justifyContent: "space-between" }}>
          <Typography component="dt" variant="body2" sx={{ color: "text.secondary" }}>
            {row.label}
          </Typography>
          <Typography component="dd" variant="body2" sx={{ m: 0, textAlign: "right" }}>
            {row.value}
          </Typography>
        </Stack>
      ))}
      <Typography variant="caption" sx={{ color: "text.disabled" }}>
        {t("sheet.step", { n: stepNumber })}
      </Typography>
    </Stack>
  );

  if (collapsed) {
    return (
      <Accordion component="section" aria-label={t("sheet.heading")}>
        <AccordionSummary expandIcon={<ChevronDown size={16} aria-hidden />}>
          <Typography>{stripLabel}</Typography>
        </AccordionSummary>
        <AccordionDetails>{fieldList}</AccordionDetails>
      </Accordion>
    );
  }

  return (
    <Box component="aside" aria-label={t("sheet.heading")}>
      {fieldList}
    </Box>
  );
}
