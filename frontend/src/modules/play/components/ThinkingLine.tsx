// The "Dungeon Master is thinking" line (sprint 010/07 WI2 ← AC2, AC4):
// a small spinner plus one wording, shown at the foot of the transcript
// only while a turn runs. `Transcript.tsx` owns *when* this mounts (so
// rolls and system lines already in the transcript stay above it, AC2);
// this component only draws the line itself, `data-testid="thinking-line"`
// on its root so the transcript's own tests can find it, and wraps the
// text in `aria-live="polite"` so assistive tech announces it once,
// without interrupting whatever else is being read (D12).
import type { ReactElement } from "react";
import Stack from "@mui/material/Stack";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

export function ThinkingLine(): ReactElement {
  const { t } = useTranslation("play");

  return (
    <Stack
      direction="row"
      spacing={2}
      data-testid="thinking-line"
      aria-live="polite"
      sx={{ alignItems: "center", justifyContent: "center" }}
    >
      <CircularProgress size={16} aria-hidden />
      <Typography variant="body2" sx={{ color: "text.secondary" }}>
        {t("thinking.first")}
      </Typography>
    </Stack>
  );
}
