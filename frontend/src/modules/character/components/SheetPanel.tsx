// The live "your sheet so far" panel (sprint 009-06, WI1, AC3, research.md
// Decision 6): one field list, rendered once, wrapped in whichever frame the
// caller picked via `collapsed` — a side panel on a wide screen, or an
// Accordion whose closed summary is the narrow-screen strip. `collapsed` is
// a plain prop, not a `useMediaQuery` call in here, so this component stays
// trivially testable at both sizes without depending on the test suite's
// `matchMedia` stub (frontend-stack.md "Test arrangement"; research.md
// facts).
//
// Creation-chat viewport fix: the wide frame is a raised card that scrolls
// on its own inside the rail its caller sizes (`maxHeight: 100%`); the
// narrow Accordion caps its opened details at `40dvh` so the chat below
// stays reachable. The field list is still one `<dl>`, grouped by dividers:
// identity rows, the six abilities as a 3×2 grid of cells, hit points and
// armour class as two more cells, then skills and equipment with the label
// stacked above the value. The cells come from `StatCells`, shared with
// `ReviewPanel`.
import type { ReactElement } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { SheetSoFar } from "../hooks/useCreationChat";
import { StatCells } from "./StatCells";

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
  const identity: FieldRow[] = [
    { label: t("sheet.fields.name"), value: sheet?.name ?? empty },
    { label: t("sheet.fields.race"), value: sheet?.race ?? empty },
    { label: t("sheet.fields.class"), value: sheet?.characterClass ?? empty },
    { label: t("sheet.fields.level"), value: sheet?.level != null ? String(sheet.level) : empty },
    { label: t("sheet.fields.alignment"), value: sheet?.alignment ?? empty },
  ];
  const abilityRows: FieldRow[] = [
    { label: t("sheet.fields.abilities.str"), value: abilities ? String(abilities.strength) : empty },
    { label: t("sheet.fields.abilities.dex"), value: abilities ? String(abilities.dexterity) : empty },
    { label: t("sheet.fields.abilities.con"), value: abilities ? String(abilities.constitution) : empty },
    { label: t("sheet.fields.abilities.int"), value: abilities ? String(abilities.intelligence) : empty },
    { label: t("sheet.fields.abilities.wis"), value: abilities ? String(abilities.wisdom) : empty },
    { label: t("sheet.fields.abilities.cha"), value: abilities ? String(abilities.charisma) : empty },
  ];
  const vitals: FieldRow[] = [
    { label: t("sheet.fields.hitPoints"), value: sheet?.maxHp != null ? String(sheet.maxHp) : empty },
    { label: t("sheet.fields.armourClass"), value: sheet?.armourClass != null ? String(sheet.armourClass) : empty },
  ];
  const lists: FieldRow[] = [
    { label: t("sheet.fields.skills"), value: formatList(sheet?.skills, empty) },
    { label: t("sheet.fields.equipment"), value: formatList(sheet?.equipment, empty) },
  ];

  const raceClass = [sheet?.race, sheet?.characterClass].filter(Boolean).join(" ") || empty;
  const level = sheet?.level != null ? String(sheet.level) : empty;
  const stripLabel = t("sheet.strip", { raceClass, level, n: stepNumber });

  const fieldList = (
    <Stack spacing={4}>
      <Stack direction="row" spacing={2} sx={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <Typography variant="overline" sx={{ fontFamily: "var(--font-smallcaps)", color: "text.secondary" }}>
          {t("sheet.heading")}
        </Typography>
        <Typography variant="caption" sx={{ color: "text.disabled" }}>
          {t("sheet.step", { n: stepNumber })}
        </Typography>
      </Stack>
      <Stack spacing={3} component="dl" divider={<Divider flexItem />} sx={{ m: 0 }}>
        <Stack spacing={2}>
          {identity.map((row) => (
            <Stack key={row.label} direction="row" spacing={2} sx={{ justifyContent: "space-between" }}>
              <Typography component="dt" variant="body2" sx={{ color: "text.secondary" }}>
                {row.label}
              </Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0, textAlign: "right" }}>
                {row.value}
              </Typography>
            </Stack>
          ))}
        </Stack>
        <StatCells rows={abilityRows} columns="repeat(3, 1fr)" />
        <StatCells rows={vitals} columns="repeat(2, 1fr)" mono />
        <Stack spacing={3}>
          {lists.map((row) => (
            <Stack key={row.label} spacing={1}>
              <Typography component="dt" variant="body2" sx={{ color: "text.secondary" }}>
                {row.label}
              </Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>
                {row.value}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Stack>
    </Stack>
  );

  if (collapsed) {
    return (
      <Accordion
        component="section"
        aria-label={t("sheet.heading")}
        variant="outlined"
        square
        disableGutters
        sx={(theme) => ({
          borderRadius: theme.shape.borderRadiusOrganicSoft,
          boxShadow: theme.shadows[5],
          "&::before": { display: "none" },
        })}
      >
        <AccordionSummary expandIcon={<ChevronDown size={16} aria-hidden />} sx={{ px: 5 }}>
          <Typography variant="body2">{stripLabel}</Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ px: 5, pb: 5, pt: 0, maxHeight: "40dvh", overflowY: "auto" }}>
          {fieldList}
        </AccordionDetails>
      </Accordion>
    );
  }

  return (
    <Card
      variant="outlined"
      component="aside"
      aria-label={t("sheet.heading")}
      sx={(theme) => ({
        borderRadius: theme.shape.borderRadiusOrganic,
        boxShadow: theme.shadows[5],
        maxHeight: "100%",
        overflowY: "auto",
      })}
    >
      <CardContent sx={{ p: 5, "&:last-child": { pb: 5 } }}>{fieldList}</CardContent>
    </Card>
  );
}
