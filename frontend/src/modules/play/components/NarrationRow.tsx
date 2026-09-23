// One of the transcript's four row kinds (D12 §2, sprint 010/06 WI2): the
// Dungeon Master's own words, left-aligned, named and timed. Covers
// `narration` and `question` alike -- `transcript.ts` maps both to the same
// `"narration"` row kind, a question's answer buttons being a later
// sprint's concern (README.md).
import type { ReactElement } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { formatClockTime } from "./formatClockTime";

export interface NarrationRowProps {
  text: string;
  at: string;
}

export function NarrationRow({ text, at }: NarrationRowProps): ReactElement {
  const { t, i18n } = useTranslation("play");

  return (
    <Box component="article" sx={{ display: "grid", gap: 1 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", justifyContent: "space-between" }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <ChevronRight size={14} aria-hidden color="var(--accent)" />
          <Typography
            variant="subtitle2"
            sx={{ fontFamily: "var(--font-display)", fontWeight: "var(--weight-bold)" }}
          >
            {t("narration.author")}
          </Typography>
        </Stack>
        <Typography
          component="time"
          dateTime={at}
          variant="caption"
          sx={{ color: "text.muted", fontFamily: "var(--font-mono)" }}
        >
          {formatClockTime(at, i18n.language)}
        </Typography>
      </Stack>
      <Typography sx={{ color: "text.primary" }}>{text}</Typography>
    </Box>
  );
}
