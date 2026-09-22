// The conversation itself (sprint 009-06, WI1, AC2/AC5): one row per turn,
// labelled through `chat.keeper`/`chat.you` — the agent's on-screen name
// lives only in that locale value (D15), never in an identifier here. A
// failed turn (an `error: true` reply, already rendered as a keeper turn by
// `useCreationChat`, or a thrown request failure it renders in its place)
// adds one retry affordance below the transcript; the conversation itself
// never disappears (← AC5, D16 §1.17).
import type { ReactElement } from "react";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { ChatTurn } from "../hooks/useCreationChat";

export interface TranscriptProps {
  turns: ChatTurn[];
  failed: boolean;
  onRetry: () => void;
}

export function Transcript({ turns, failed, onRetry }: TranscriptProps): ReactElement {
  const { t } = useTranslation("character");
  const { t: tCommon } = useTranslation("common");

  const lastIndex = turns.length - 1;

  return (
    <Stack spacing={3} component="ol" sx={{ m: 0, p: 0, listStyle: "none" }}>
      {turns.map((turn, index) => (
        // The transcript only ever appends; nothing before an index is ever
        // reordered or removed, so the index is a stable key for this
        // list's whole lifetime.
        <Stack key={index} component="li" spacing={1}>
          <Typography variant="overline" sx={{ color: "text.secondary" }}>
            {turn.speaker === "keeper" ? t("chat.keeper") : t("chat.you")}
          </Typography>
          <Typography role={failed && index === lastIndex ? "alert" : undefined}>{turn.text}</Typography>
        </Stack>
      ))}
      {failed && (
        <Button variant="outlined" size="small" onClick={onRetry} sx={{ alignSelf: "flex-start" }}>
          {tCommon("actions.retry")}
        </Button>
      )}
    </Stack>
  );
}
