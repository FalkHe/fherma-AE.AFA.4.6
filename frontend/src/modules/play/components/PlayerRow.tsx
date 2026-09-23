// One of the transcript's four row kinds (D12 §2, sprint 010/06 WI2): the
// player's own words, right-aligned under the character's name -- `author`
// is always the hero's name (`transcript.ts`'s `player_action` mapping,
// D9's one hero per run), never translated: a character's name is game
// content, not interface copy.
import type { ReactElement } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { ChevronLeft } from "lucide-react";
import { useTranslation } from "react-i18next";

import { formatClockTime } from "./formatClockTime";

export interface PlayerRowProps {
  author: string;
  text: string;
  at: string;
}

export function PlayerRow({ author, text, at }: PlayerRowProps): ReactElement {
  const { i18n } = useTranslation("play");

  return (
    <Box component="article" sx={{ display: "grid", gap: 1, justifyItems: "end" }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
        <Typography
          component="time"
          dateTime={at}
          variant="caption"
          sx={{ color: "text.muted", fontFamily: "var(--font-mono)" }}
        >
          {formatClockTime(at, i18n.language)}
        </Typography>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <Typography
            variant="subtitle2"
            sx={{ fontFamily: "var(--font-display)", fontWeight: "var(--weight-bold)" }}
          >
            {author}
          </Typography>
          <ChevronLeft size={14} aria-hidden color="var(--accent-secondary)" />
        </Stack>
      </Stack>
      <Typography sx={{ color: "text.primary", textAlign: "right", maxWidth: "80%" }}>{text}</Typography>
    </Box>
  );
}
