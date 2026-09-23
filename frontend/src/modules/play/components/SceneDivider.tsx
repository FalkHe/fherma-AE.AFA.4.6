// One row the transcript draws between the four D12 §2 kinds, not one of
// them: a divider closing the previous scene and naming the new one
// (`scene_entered` in `transcript.ts`, D12 §1.11).
import type { ReactElement } from "react";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";

export interface SceneDividerProps {
  scene: string;
}

export function SceneDivider({ scene }: SceneDividerProps): ReactElement {
  return (
    // A divider that wraps text is best rendered `role="presentation"`
    // (MUI's own accessibility guidance for this pattern) so the scene name
    // reads as ordinary text rather than being announced as a bare
    // separator with no content.
    <Divider
      role="presentation"
      sx={{
        my: 2,
        "&::before, &::after": { borderColor: "var(--border-soft)" },
      }}
    >
      <Typography
        variant="overline"
        sx={{ color: "text.secondary", letterSpacing: "var(--ls-label)", px: 2 }}
      >
        {scene}
      </Typography>
    </Divider>
  );
}
