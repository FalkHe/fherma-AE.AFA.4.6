// One of the transcript's four row kinds (D12 §2, sprint 010/06 WI2): a
// small, centred line between dots -- never a paragraph. The game writes no
// wording at all: a system row arrives as a bare `SystemKey` plus `values`
// (`transcript.ts`), and this is the one place that words it, by looking
// `system.<key>` up in the `play` i18n namespace and interpolating those
// values -- the whole point of AC3 (sprint brief). The leading/trailing "·"
// is D12's own layout punctuation, added once here rather than baked into
// each of the seven strings.
import type { ReactElement } from "react";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { SystemKey } from "../transcript";

export interface SystemLineProps {
  systemKey: SystemKey;
  values: Record<string, string | number>;
}

export function SystemLine({ systemKey, values }: SystemLineProps): ReactElement {
  const { t } = useTranslation("play");

  return (
    <Typography
      variant="body2"
      align="center"
      noWrap
      sx={{
        color: "text.secondary",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-small)",
        overflow: "hidden",
        textOverflow: "ellipsis",
      }}
    >
      {`· ${t(`system.${systemKey}`, values)} ·`}
    </Typography>
  );
}
