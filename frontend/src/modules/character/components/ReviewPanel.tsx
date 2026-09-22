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
import type { ReactElement } from "react";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { SheetSoFar } from "../hooks/useCreationChat";

export interface ReviewPanelProps {
  sheet: SheetSoFar;
  failed: boolean;
  errorText: string;
  onSave: () => void;
  onChange: () => void;
}

interface FieldRow {
  label: string;
  value: string;
}

function formatModifier(score: number): string {
  const modifier = Math.floor((score - 10) / 2);
  // U+2212 MINUS SIGN, matching D14's wireframe ("−1") rather than a hyphen.
  return modifier >= 0 ? `+${modifier}` : `−${Math.abs(modifier)}`;
}

function formatList(values: string[] | undefined, empty: string): string {
  return values && values.length > 0 ? values.join(", ") : empty;
}

export function ReviewPanel({ sheet, failed, errorText, onSave, onChange }: ReviewPanelProps): ReactElement {
  const { t } = useTranslation("character");
  const empty = t("sheet.empty");
  const abilities = sheet.abilities ?? null;

  function abilityRow(label: string, score: number | undefined): FieldRow {
    return { label, value: score != null ? `${score} (${formatModifier(score)})` : empty };
  }

  const rows: FieldRow[] = [
    { label: t("sheet.fields.name"), value: sheet.name ?? empty },
    { label: t("sheet.fields.race"), value: sheet.race ?? empty },
    { label: t("sheet.fields.class"), value: sheet.characterClass ?? empty },
    { label: t("sheet.fields.level"), value: sheet.level != null ? String(sheet.level) : empty },
    { label: t("sheet.fields.alignment"), value: sheet.alignment ?? empty },
    { label: t("sheet.fields.hitPoints"), value: sheet.maxHp != null ? String(sheet.maxHp) : empty },
    { label: t("sheet.fields.armourClass"), value: sheet.armourClass != null ? String(sheet.armourClass) : empty },
    { label: t("sheet.fields.speed"), value: sheet.speed != null ? String(sheet.speed) : empty },
    abilityRow(t("sheet.fields.abilities.str"), abilities?.strength),
    abilityRow(t("sheet.fields.abilities.dex"), abilities?.dexterity),
    abilityRow(t("sheet.fields.abilities.con"), abilities?.constitution),
    abilityRow(t("sheet.fields.abilities.int"), abilities?.intelligence),
    abilityRow(t("sheet.fields.abilities.wis"), abilities?.wisdom),
    abilityRow(t("sheet.fields.abilities.cha"), abilities?.charisma),
    { label: t("sheet.fields.skills"), value: formatList(sheet.skills, empty) },
    { label: t("sheet.fields.equipment"), value: formatList(sheet.equipment, empty) },
    { label: t("sheet.fields.looks"), value: sheet.appearance ?? empty },
    { label: t("sheet.fields.story"), value: sheet.backstory ?? empty },
  ];

  return (
    <Stack spacing={4} component="section" aria-label={t("review.title")}>
      <Stack spacing={1}>
        <Typography variant="h2" component="h2">
          {t("review.title")}
        </Typography>
        <Typography sx={{ color: "text.secondary" }}>{t("review.subtitle")}</Typography>
      </Stack>

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2} component="dl" sx={{ m: 0 }}>
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
          </Stack>
        </CardContent>
      </Card>

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
  );
}
