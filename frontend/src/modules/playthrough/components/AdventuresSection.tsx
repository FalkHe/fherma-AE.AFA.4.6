// The run screen's adventures list (sprint 007/06 WI1, AC1-AC5): one
// numbered row per adventure in campaign order, badge text derived from
// `RunAdventure.status` and the "current" row index -- never invented in
// the browser. The current row is the first adventure whose status isn't
// `done` (an `active` row included, per the sprint brief); it reads "Next
// up" when every seated member is ready, "Waiting on party" otherwise, with
// a fixed explanatory line next to the heading (decision: the condition
// comes from the API, the wording is the frontend's -- same contract
// `RunRoute`'s own status badge already uses, `routes/RunRoute.tsx:31-44`).
// Rows after the current one read "Locked", rows before it "Done".
//
// "Start adventure" renders on the current row only and is always disabled
// with no `onClick` at all (decision) -- starting an adventure isn't built
// yet, so the button can't offer to do it regardless of party readiness,
// unlike the design mock's `disabled="{{blocked}}"`
// (docs/design/dnd-app-dashboard-design/project/CampaignRun.dc.html:93). A
// disabled button takes no focus, so its hover-only MUI Tooltip
// (`<span>`-inside-`Tooltip>` pattern) only ever repeats the reason when
// that reason applies (the row is actually waiting on the party); the
// always-visible heading line is what serves keyboard and screen-reader
// users.
import type { ReactElement } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import type { ChipProps } from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { Lock } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { RunMember, RunOverview } from "../hooks/useRunOverview";

export type RunAdventure = RunOverview["adventures"][number];

export interface AdventuresSectionProps {
  adventures: RunAdventure[];
  members: RunMember[];
}

type AdventureStatusKey =
  | "adventures.status.nextUp"
  | "adventures.status.waitingOnParty"
  | "adventures.status.locked"
  | "adventures.status.done";

const STATUS_CHIP_COLOR: Record<AdventureStatusKey, ChipProps["color"]> = {
  "adventures.status.nextUp": "primary",
  "adventures.status.waitingOnParty": "default",
  "adventures.status.locked": "default",
  "adventures.status.done": "secondary",
};

// Roman numerals for the row index -- the design's own numbering
// (docs/design/dnd-app-dashboard-design/project/CampaignRun.dc.html:83),
// not a translated string (sprint brief's API facts: "no i18n key, no
// library"). An adventure list never runs long enough to need more than
// this low-tens table.
const ROMAN_NUMERALS: ReadonlyArray<readonly [number, string]> = [
  [1000, "M"],
  [900, "CM"],
  [500, "D"],
  [400, "CD"],
  [100, "C"],
  [90, "XC"],
  [50, "L"],
  [40, "XL"],
  [10, "X"],
  [9, "IX"],
  [5, "V"],
  [4, "IV"],
  [1, "I"],
];

function toRoman(value: number): string {
  let remaining = value;
  let result = "";
  for (const [amount, numeral] of ROMAN_NUMERALS) {
    while (remaining >= amount) {
      result += numeral;
      remaining -= amount;
    }
  }
  return result;
}

interface AdventureRowProps {
  adventure: RunAdventure;
  numeral: string;
  statusKey: AdventureStatusKey;
  isCurrent: boolean;
}

function AdventureRow({ adventure, numeral, statusKey, isCurrent }: AdventureRowProps): ReactElement {
  const { t } = useTranslation("playthrough");
  const isLocked = statusKey === "adventures.status.locked";
  const isWaiting = statusKey === "adventures.status.waitingOnParty";

  const startButton = (
    <Tooltip title={t("adventures.waitingHint")} disableHoverListener={!isWaiting}>
      <span>
        <Button variant="outlined" size="small" disabled>
          {t("adventures.start")}
        </Button>
      </span>
    </Tooltip>
  );

  return (
    <Card
      variant="outlined"
      sx={(theme) => ({
        borderRadius: theme.shape.borderRadiusOrganic,
        opacity: isLocked ? 0.6 : 1,
        backgroundColor: isCurrent ? theme.palette.background.paper : "var(--surface-inset)",
      })}
    >
      <Stack direction="row" spacing={4} sx={{ alignItems: "center", p: 4, flexWrap: { xs: "wrap", sm: "nowrap" } }}>
        <Box
          sx={(theme) => ({
            width: 44,
            height: 44,
            flex: "0 0 auto",
            display: "grid",
            placeItems: "center",
            borderRadius: theme.shape.borderRadiusOrganicSoft,
            backgroundColor: "var(--surface-inset)",
            border: "1px solid var(--border-strong)",
            fontFamily: "var(--font-display)",
            color: isCurrent ? "var(--accent)" : "var(--text-muted)",
          })}
        >
          {numeral}
        </Box>

        <Box sx={{ minWidth: 0, flex: 1, display: "grid", gap: 1 }}>
          <Stack direction="row" spacing={3} sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <Typography sx={{ fontFamily: "var(--font-display)", fontWeight: "var(--weight-bold)" }}>
              {adventure.title}
            </Typography>
            <Chip label={t(statusKey)} size="small" color={STATUS_CHIP_COLOR[statusKey]} />
          </Stack>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            {adventure.introExcerpt}
          </Typography>
        </Box>

        <Box sx={{ flex: "0 0 auto" }}>
          {isCurrent && startButton}
          {isLocked && <Lock size={16} aria-hidden color="var(--text-muted)" />}
        </Box>
      </Stack>
    </Card>
  );
}

export function AdventuresSection({ adventures, members }: AdventuresSectionProps): ReactElement {
  const { t } = useTranslation("playthrough");

  const partyReady = members.length > 0 && members.every((member) => member.ready);
  const currentIndex = adventures.findIndex((adventure) => adventure.status !== "done");
  const isBlocked = !partyReady && currentIndex !== -1;

  return (
    <Stack spacing={4} component="section">
      <Stack direction="row" spacing={4} sx={{ alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
        <Typography variant="overline" sx={{ color: "text.secondary" }}>
          {t("adventures.heading")}
        </Typography>
        {isBlocked && (
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            {t("adventures.waitingHint")}
          </Typography>
        )}
      </Stack>

      <Stack spacing={3}>
        {adventures.map((adventure, index) => {
          const isCurrent = index === currentIndex;
          const statusKey: AdventureStatusKey =
            adventure.status === "done"
              ? "adventures.status.done"
              : isCurrent
                ? partyReady
                  ? "adventures.status.nextUp"
                  : "adventures.status.waitingOnParty"
                : "adventures.status.locked";

          return (
            <AdventureRow
              key={adventure.id}
              adventure={adventure}
              numeral={toRoman(index + 1)}
              statusKey={statusKey}
              isCurrent={isCurrent}
            />
          );
        })}
      </Stack>
    </Stack>
  );
}
