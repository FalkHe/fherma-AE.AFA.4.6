// The pending question / pending roll prompt (sprint 010/09 WI3 ← AC1,
// AC3). Two mutually exclusive shapes on the wire (`transcript.ts`'s
// `PendingPrompt`): a `choice` prompt draws one button per option, its
// text verbatim off the wire (never through `t()` -- it is the Dungeon
// Master's own wording, same reasoning as `DiceChip`'s game data); a
// `roll` prompt draws exactly one button, its label composed from
// `roll.button` with the notation interpolated in. Either way this is the
// only way to answer while a prompt is open (AC1): no free-text field, no
// other control, nothing here calls the network itself -- `onChoose`/
// `onRoll` are the one way out, same shape as `Composer`'s `onSend`.
// Options stack full-width on a narrow screen, matching the module's
// `xs`/`sm` breakpoint convention (`playthrough/components/CampaignCta.tsx`).
import type { ReactElement } from "react";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import { useTranslation } from "react-i18next";

import type { PendingPrompt as PendingPromptModel } from "../transcript";

export interface PendingPromptProps {
  prompt: PendingPromptModel;
  onChoose: (option: string) => void;
  onRoll: () => void;
}

export function PendingPrompt({ prompt, onChoose, onRoll }: PendingPromptProps): ReactElement {
  const { t } = useTranslation("play");

  if (prompt.kind === "roll") {
    return (
      <Stack direction="row" sx={{ justifyContent: "center" }}>
        <Button variant="contained" fullWidth sx={{ maxWidth: { sm: 320 } }} onClick={onRoll}>
          {t("roll.button", { notation: prompt.notation })}
        </Button>
      </Stack>
    );
  }

  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ width: "100%" }}>
      {prompt.options.map((option) => (
        <Button key={option} variant="outlined" fullWidth onClick={() => onChoose(option)}>
          {option}
        </Button>
      ))}
    </Stack>
  );
}
