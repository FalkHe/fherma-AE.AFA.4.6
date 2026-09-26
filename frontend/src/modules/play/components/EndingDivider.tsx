// The transcript's closing marker (defect fix, ← `finish_run`'s `system`
// event, `transcript.ts`'s `"ending"` row): a centred divider, styled like
// `SceneDivider`, naming how the adventure ended. Worded through i18n
// (`play.json`'s `ending.<outcome>`), never the wire's own English prose --
// same stance as `SystemLine`.
import type { ReactElement } from "react";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { RunOutcome } from "../transcript";

export interface EndingDividerProps {
  outcome: RunOutcome;
}

export function EndingDivider({ outcome }: EndingDividerProps): ReactElement {
  const { t } = useTranslation("play");

  return (
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
        {t(`ending.${outcome}`)}
      </Typography>
    </Divider>
  );
}
