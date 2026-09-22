// The step's fixed set of buttons, if it has one (sprint 009-06, WI1, AC2,
// research.md Decision 2 as amended by plan.md I1): a `step -> choices` map,
// not anything parsed out of the reply's prose. Each button sends exactly
// its own label text — a click and typing the same words are literally the
// same request (← D14 §1.6/§1.11).
//
// `hasPlayerTurn` is this component's one addition over the plan's literal
// prop list: the gate offer ("Take <name>" / "Make my own") only belongs on
// the very first reply, before the player has said anything — `stepNumber`
// alone stays at 1 for several turns afterwards while the build path still
// settles race and class (D14 §1.4-1.5), so `stepNumber === 1` on its own
// would repeat the gate buttons mid-conversation.
import type { ReactElement } from "react";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import { useTranslation } from "react-i18next";

import type { CreationStep } from "../hooks/useCreationChat";

export interface OfferedChoicesProps {
  step: CreationStep | null;
  stepNumber: number;
  readyMadeName: string | null;
  hasPlayerTurn: boolean;
  onPick: (text: string) => void;
}

export function OfferedChoices({
  step,
  stepNumber,
  readyMadeName,
  hasPlayerTurn,
  onPick,
}: OfferedChoicesProps): ReactElement | null {
  const { t } = useTranslation("character");

  if (stepNumber === 1 && !hasPlayerTurn) {
    const takeLabel = readyMadeName ? t("choices.takeReadyMade", { name: readyMadeName }) : null;
    const makeLabel = t("choices.makeMyOwn");
    return (
      <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap" }}>
        {takeLabel && (
          <Button variant="outlined" onClick={() => onPick(takeLabel)}>
            {takeLabel}
          </Button>
        )}
        <Button variant="outlined" onClick={() => onPick(makeLabel)}>
          {makeLabel}
        </Button>
      </Stack>
    );
  }

  if (step === "scores") {
    const suggestLabel = t("choices.suggestScores");
    const rollLabel = t("choices.rollScores");
    const spendLabel = t("choices.spendScores");
    return (
      <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap" }}>
        <Button variant="outlined" onClick={() => onPick(suggestLabel)}>
          {suggestLabel}
        </Button>
        <Button variant="outlined" onClick={() => onPick(rollLabel)}>
          {rollLabel}
        </Button>
        <Button variant="outlined" onClick={() => onPick(spendLabel)}>
          {spendLabel}
        </Button>
      </Stack>
    );
  }

  if (step === "equipment") {
    const defaultLabel = t("choices.defaultEquipment");
    return (
      <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap" }}>
        <Button variant="outlined" onClick={() => onPick(defaultLabel)}>
          {defaultLabel}
        </Button>
      </Stack>
    );
  }

  return null;
}
