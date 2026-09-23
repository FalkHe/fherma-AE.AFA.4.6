// One of the transcript's four row kinds (D12 §2, sprint 010/06 WI2): the
// dice result, centred. `label`, `notation`, `breakdown` and `total` are
// all game data off `transcript.ts`'s `dice` row, not interface copy, so
// none of it goes through `t()`. `verdict` (sprint 010/09 WI3 ← AC4) is the
// one exception: whether the row's own row-builder can now say a roll made
// or missed its check, drawn as a ✓/✗ beside the total, named for
// accessibility via `dice.madeIt`/`dice.missed`. Optional and undrawn when
// absent -- a roll with no check to beat (damage, initiative, a plain
// request) has no verdict at all.
import type { ReactElement } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Check, X } from "lucide-react";
import { useTranslation } from "react-i18next";

export interface DiceChipProps {
  label: string;
  notation: string;
  breakdown: string;
  total: number;
  verdict?: "madeIt" | "missed";
}

export function DiceChip({ label, notation, breakdown, total, verdict }: DiceChipProps): ReactElement {
  const { t } = useTranslation("play");

  return (
    <Box
      role="group"
      sx={(theme) => ({
        mx: "auto",
        minWidth: 220,
        display: "grid",
        gap: 1,
        p: 3,
        borderRadius: theme.shape.borderRadiusOrganicSoft,
        backgroundColor: "var(--surface-timber)",
        border: "1px solid var(--border-timber)",
      })}
    >
      <Stack direction="row" spacing={4} sx={{ alignItems: "baseline", justifyContent: "space-between" }}>
        <Typography variant="body2" sx={{ fontWeight: "var(--weight-bold)" }}>
          {label}
        </Typography>
        <Typography variant="body2" sx={{ fontFamily: "var(--font-mono)", color: "text.secondary" }}>
          {notation}
        </Typography>
      </Stack>
      <Stack direction="row" spacing={4} sx={{ alignItems: "baseline", justifyContent: "space-between" }}>
        <Typography variant="body2" sx={{ fontFamily: "var(--font-mono)", color: "text.secondary" }}>
          {breakdown}
        </Typography>
        <Stack direction="row" spacing={1} sx={{ alignItems: "baseline" }}>
          <Typography variant="body2" sx={{ fontFamily: "var(--font-mono)", fontWeight: "var(--weight-bold)" }}>
            {total}
          </Typography>
          {verdict !== undefined && (
            <Box
              component="span"
              role="img"
              aria-label={verdict === "madeIt" ? t("dice.madeIt") : t("dice.missed")}
              sx={{ display: "inline-flex", color: verdict === "madeIt" ? "success.main" : "error.main" }}
            >
              {verdict === "madeIt" ? <Check size={16} aria-hidden /> : <X size={16} aria-hidden />}
            </Box>
          )}
        </Stack>
      </Stack>
    </Box>
  );
}
