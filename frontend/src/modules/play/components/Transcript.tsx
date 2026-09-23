// The play screen's transcript (D12 §2, sprint 010/06 WI2): the four row
// kinds it draws and no others -- narration, player, system and dice --
// plus scene dividers between them and the empty line before anything is
// recorded. Rows are pure data off `transcript.ts`'s `TranscriptRow` union;
// this component's only job is drawing each kind D12's way and wording the
// system rows through i18n (AC3) -- it invents nothing (no verdict on the
// dice chip, no difficulty on the check line, ← sprint brief).
//
// Also mounts the "Jump to the latest" pill (WI3's `useStickToLatest` /
// `JumpToLatestPill`, built in parallel on this branch): `scrollRef` goes
// on the scrolling element, and the pill only ever appears while
// `!atBottom` (D12 §2 -- "scrolling up puts a Jump to the latest pill at
// the foot of it").
import type { ReactElement } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { TranscriptRow } from "../transcript";
import { useStickToLatest } from "../hooks/useStickToLatest";
import { JumpToLatestPill } from "./JumpToLatestPill";
import { NarrationRow } from "./NarrationRow";
import { PlayerRow } from "./PlayerRow";
import { SystemLine } from "./SystemLine";
import { DiceChip } from "./DiceChip";
import { SceneDivider } from "./SceneDivider";

export interface TranscriptProps {
  rows: TranscriptRow[];
}

function renderRow(row: TranscriptRow): ReactElement {
  switch (row.kind) {
    case "narration":
      return <NarrationRow key={row.id} text={row.text} at={row.at} />;
    case "player":
      return <PlayerRow key={row.id} author={row.author} text={row.text} at={row.at} />;
    case "system":
      return <SystemLine key={row.id} systemKey={row.key} values={row.values} />;
    case "dice":
      return (
        <DiceChip key={row.id} label={row.label} notation={row.notation} breakdown={row.breakdown} total={row.total} />
      );
    case "divider":
      return <SceneDivider key={row.id} scene={row.scene} />;
  }
}

export function Transcript({ rows }: TranscriptProps): ReactElement {
  const { t } = useTranslation("play");
  const { scrollRef, atBottom, jumpToLatest } = useStickToLatest();

  return (
    <Box sx={{ position: "relative" }}>
      <Box
        ref={scrollRef}
        role="log"
        sx={(theme) => ({
          display: "grid",
          gap: 4,
          maxHeight: "100%",
          overflowY: "auto",
          p: 4,
          borderRadius: theme.shape.borderRadiusOrganic,
          backgroundColor: "var(--surface-card)",
          border: "1px solid var(--border-hairline)",
        })}
      >
        {rows.length === 0 ? (
          <Typography sx={{ color: "text.secondary", textAlign: "center" }}>{t("empty")}</Typography>
        ) : (
          rows.map(renderRow)
        )}
      </Box>

      {!atBottom && (
        <Box sx={{ position: "sticky", bottom: 16, display: "flex", justifyContent: "center", mt: -8 }}>
          <JumpToLatestPill onClick={jumpToLatest} />
        </Box>
      )}
    </Box>
  );
}
