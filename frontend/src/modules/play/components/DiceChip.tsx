// One of the transcript's four row kinds (D12 §2, sprint 010/06 WI2): the
// dice result, centred. `label`, `notation`, `breakdown` and `total` are
// all game data off `transcript.ts`'s `dice` row, not interface copy, so
// none of it goes through `t()`. Deliberately missing D12's verdict mark
// (✓ made it / ✗ missed): whether a roll made its check is never recorded
// anywhere a player can read it, so this sprint renders the chip without
// one rather than inventing it (sprint brief, `research.md`).
import type { ReactElement } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

export interface DiceChipProps {
  label: string;
  notation: string;
  breakdown: string;
  total: number;
}

export function DiceChip({ label, notation, breakdown, total }: DiceChipProps): ReactElement {
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
        <Typography variant="body2" sx={{ fontFamily: "var(--font-mono)", fontWeight: "var(--weight-bold)" }}>
          {total}
        </Typography>
      </Stack>
    </Box>
  );
}
