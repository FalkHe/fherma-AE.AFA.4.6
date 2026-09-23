// The finished sheet, laid out for a final look before it is written down
// for good (sprint 009-07, WI1, AC1/AC2/AC5, D9/D14 §3): replaces
// `Transcript` + `OfferedChoices` as a state of the creation page
// (research.md Decision 1) once `step === "review" && canSave`. Ability
// modifiers are computed here, in the browser, over numbers the backend
// already fixed (research.md Decision 3) — `Math.floor((score - 10) / 2)`,
// formatted with a real minus sign (U+2212), never a hyphen, to match D14's
// wireframe ("−1").
//
// `onSave`/`onChange` take no argument, same shape as `LeaveDialog`'s
// `onStay`/`onLeave` — the caller (`CreationChatRoute`) sends each button's
// own label text as the player's message (← D14 §1.12, same rule
// `OfferedChoices` follows), this component only renders the copy and fires
// the intent.
//
// Creation-chat viewport fix: the panel fills the transcript well's bounded
// box, full width (the route drops the sheet rail while it shows) — the
// title stays at the top, the sheet card scrolls on its own, and the error
// line plus both buttons stay pinned at the panel's foot. The card reads as
// a character sheet: name and identity line beside the vitals, the six
// abilities as `StatCells` with their modifiers, skills and equipment as
// chips, then looks and story as prose. Every labelled value is a `dt`/`dd`
// pair; the name is the card's heading instead, and race, class, level and
// alignment share the one identity line under it.
import type { ReactElement } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { SheetSoFar } from "../hooks/useCreationChat";
import { type StatCell, StatCells } from "./StatCells";

export interface ReviewPanelProps {
  sheet: SheetSoFar;
  failed: boolean;
  errorText: string;
  onSave: () => void;
  onChange: () => void;
}

function formatModifier(score: number): string {
  const modifier = Math.floor((score - 10) / 2);
  // U+2212 MINUS SIGN, matching D14's wireframe ("−1") rather than a hyphen.
  return modifier >= 0 ? `+${modifier}` : `−${Math.abs(modifier)}`;
}

const labelSx = {
  display: "block",
  fontFamily: "var(--font-smallcaps)",
  color: "text.secondary",
} as const;

export function ReviewPanel({ sheet, failed, errorText, onSave, onChange }: ReviewPanelProps): ReactElement {
  const { t } = useTranslation("character");
  const empty = t("sheet.empty");
  const abilities = sheet.abilities ?? null;

  function abilityCell(label: string, score: number | undefined): StatCell {
    if (score == null) {
      return { label, value: empty };
    }
    return { label, value: String(score), modifier: { text: formatModifier(score), negative: score < 10 } };
  }

  const identity = t("review.identity", {
    raceClass: [sheet.race, sheet.characterClass].filter(Boolean).join(" ") || empty,
    level: sheet.level != null ? String(sheet.level) : empty,
    alignment: sheet.alignment ?? empty,
  });

  const vitals: StatCell[] = [
    { label: t("sheet.fields.hitPoints"), value: sheet.maxHp != null ? String(sheet.maxHp) : empty },
    { label: t("sheet.fields.armourClass"), value: sheet.armourClass != null ? String(sheet.armourClass) : empty },
    { label: t("sheet.fields.speed"), value: sheet.speed != null ? String(sheet.speed) : empty },
  ];

  const abilityCells: StatCell[] = [
    abilityCell(t("sheet.fields.abilities.str"), abilities?.strength),
    abilityCell(t("sheet.fields.abilities.dex"), abilities?.dexterity),
    abilityCell(t("sheet.fields.abilities.con"), abilities?.constitution),
    abilityCell(t("sheet.fields.abilities.int"), abilities?.intelligence),
    abilityCell(t("sheet.fields.abilities.wis"), abilities?.wisdom),
    abilityCell(t("sheet.fields.abilities.cha"), abilities?.charisma),
  ];

  const lists = [
    { label: t("sheet.fields.skills"), values: sheet.skills ?? [] },
    { label: t("sheet.fields.equipment"), values: sheet.equipment ?? [] },
  ];

  const prose = [
    { label: t("sheet.fields.looks"), value: sheet.appearance ?? empty },
    { label: t("sheet.fields.story"), value: sheet.backstory ?? empty },
  ];

  return (
    <Stack spacing={4} component="section" aria-label={t("review.title")} sx={{ flex: 1, minHeight: 0 }}>
      <Stack spacing={1} sx={{ flexShrink: 0 }}>
        <Typography variant="h4" component="h2">
          {t("review.title")}
        </Typography>
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          {t("review.subtitle")}
        </Typography>
      </Stack>

      <Card
        variant="outlined"
        sx={(theme) => ({
          borderRadius: theme.shape.borderRadiusOrganic,
          boxShadow: theme.shadows[5],
          minHeight: 0,
          overflowY: "auto",
        })}
      >
        <CardContent sx={{ p: { xs: 5, md: 7 }, "&:last-child": { pb: { xs: 5, md: 7 } } }}>
          <Stack spacing={6} divider={<Divider flexItem />}>
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr", md: "minmax(0, 1fr) auto" },
                gap: 6,
                alignItems: "start",
              }}
            >
              <Stack spacing={1} sx={{ minWidth: 0 }}>
                <Typography variant="h3" component="h3">
                  {sheet.name ?? empty}
                </Typography>
                <Typography sx={{ color: "text.secondary" }}>{identity}</Typography>
              </Stack>
              <StatCells
                rows={vitals}
                columns={{ xs: "repeat(3, 1fr)", md: "repeat(3, 112px)" }}
                mono
                size="roomy"
                component="dl"
              />
            </Box>

            <StatCells
              rows={abilityCells}
              columns={{ xs: "repeat(3, 1fr)", md: "repeat(6, minmax(0, 1fr))" }}
              size="roomy"
              component="dl"
            />

            <Box
              component="dl"
              sx={{ m: 0, display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 7 }}
            >
              {lists.map((list) => (
                <Stack key={list.label} spacing={2}>
                  <Typography component="dt" variant="overline" sx={labelSx}>
                    {list.label}
                  </Typography>
                  <Box component="dd" sx={{ m: 0, display: "flex", flexWrap: "wrap", gap: 2 }}>
                    {list.values.length > 0 ? (
                      list.values.map((value) => (
                        <Chip
                          key={value}
                          label={value}
                          size="small"
                          sx={{
                            bgcolor: "var(--surface-raised)",
                            border: "1px solid var(--border-soft)",
                            color: "text.secondary",
                          }}
                        />
                      ))
                    ) : (
                      <Typography>{empty}</Typography>
                    )}
                  </Box>
                </Stack>
              ))}
            </Box>

            <Stack component="dl" spacing={6} sx={{ m: 0 }}>
              {prose.map((row) => (
                <Stack key={row.label} spacing={2}>
                  <Typography component="dt" variant="overline" sx={labelSx}>
                    {row.label}
                  </Typography>
                  <Typography component="dd" sx={{ m: 0, maxWidth: "var(--width-prose)" }}>
                    {row.value}
                  </Typography>
                </Stack>
              ))}
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      <Stack spacing={4} sx={{ flexShrink: 0 }}>
        {failed && (
          <Typography role="alert" sx={{ color: "error.main" }}>
            {errorText}
          </Typography>
        )}

        <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap" }}>
          <Button variant="contained" onClick={onSave}>
            {t("review.save")}
          </Button>
          <Button variant="outlined" onClick={onChange}>
            {t("review.change")}
          </Button>
        </Stack>
      </Stack>
    </Stack>
  );
}
