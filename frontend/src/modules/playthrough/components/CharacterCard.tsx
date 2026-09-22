// The finished character, on the run screen's own player card (sprint
// 009-07, WI1, AC4, D14 §3): name, race/class/level, hit points, armour
// class, looks clamped to three lines, a "Ready" badge — no edit
// affordance, since a saved character is final for this run (D14 §1.15).
// `character` is the widened `CharacterRead` WI0 ships this sprint
// (`race`, `characterClass`, `level`, `appearance` alongside the existing
// `name`/`maxHp`/`armourClass`) — typed straight off the generated schema,
// so this component picks the fields up for free once the client is
// regenerated.
import type { ReactElement } from "react";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Shield } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { components } from "../../../api/schema";

export type Character = components["schemas"]["CharacterRead"];

export interface CharacterCardProps {
  character: Character;
}

export function CharacterCard({ character }: CharacterCardProps): ReactElement {
  const { t } = useTranslation("playthrough");

  return (
    <Card
      variant="outlined"
      sx={(theme) => ({
        borderRadius: theme.shape.borderRadiusOrganicSoft,
        backgroundColor: "var(--surface-inset)",
      })}
    >
      <CardContent sx={{ display: "grid", gap: 2 }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: "center", justifyContent: "space-between" }}>
          <Typography sx={{ fontFamily: "var(--font-display)", fontWeight: "var(--weight-bold)" }}>
            {character.name}
          </Typography>
          <Chip icon={<Shield size={14} aria-hidden />} label={t("party.card.ready")} size="small" color="primary" />
        </Stack>

        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          {t("party.card.raceClass", { race: character.race, characterClass: character.characterClass, level: character.level })}
        </Typography>

        <Stack direction="row" spacing={4}>
          <Typography variant="body2">{t("party.card.hp", { value: character.maxHp })}</Typography>
          <Typography variant="body2">{t("party.card.ac", { value: character.armourClass })}</Typography>
        </Stack>

        <Typography
          variant="body2"
          sx={{
            color: "text.secondary",
            display: "-webkit-box",
            WebkitLineClamp: 3,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {character.appearance}
        </Typography>
      </CardContent>
    </Card>
  );
}
