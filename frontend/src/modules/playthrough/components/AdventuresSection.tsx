// The run screen's adventures list (sprint 007/06 WI1, AC1-AC5; "In
// progress"/"Continue" added sprint 010/06 WI5, AC1): one numbered row per
// adventure in campaign order, badge text derived from `RunAdventure.status`
// and the "current" row index -- never invented in the browser. `status` is
// `done`/`active`/`unplayed` (`CampaignRunAdventureRead`, schema.d.ts): `done`
// always reads "Done"; `active` -- an adventure already under way -- always
// reads "In progress" with a "Continue" link to that run's play screen
// (`/runs/:runId/play`, D12 decisions doc), read via `useParams` since this
// component only ever renders under the `/runs/:runId` route. The current
// row is the first adventure whose status isn't `done`; when that row is
// still `unplayed` it reads "Next up" when every seated member is ready,
// "Waiting on party" otherwise, with a fixed explanatory line next to the
// heading (decision: the condition comes from the API, the wording is the
// frontend's -- same contract `RunRoute`'s own status badge already uses,
// `routes/RunRoute.tsx:31-44`). Rows after the current one read "Locked",
// rows before it "Done".
//
// "Start adventure" renders on the current row only, and only while it is
// still `unplayed` (never once it is under way), and is always disabled with
// no `onClick` at all (decision) -- starting an adventure isn't built yet,
// so the button can't offer to do it regardless of party readiness, unlike
// the design mock's `disabled="{{blocked}}"`
// (docs/design/dnd-app-dashboard-design/project/CampaignRun.dc.html:93). A
// disabled button takes no focus, so its hover-only MUI Tooltip
// (`<span>`-inside-`Tooltip>` pattern) only ever repeats the reason when
// that reason applies (the row is actually waiting on the party); the
// always-visible heading line is what serves keyboard and screen-reader
// users. "Start adventure" stays disabled and unwired this sprint too (D12
// decisions doc) -- only the already-under-way row's wording and link are
// new here.
import type { ReactElement } from "react";
import { Link as RouterLink, useParams } from "react-router";
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
  | "adventures.status.done"
  | "adventures.status.inProgress";

const STATUS_CHIP_COLOR: Record<AdventureStatusKey, ChipProps["color"]> = {
  "adventures.status.nextUp": "primary",
  "adventures.status.waitingOnParty": "default",
  "adventures.status.locked": "default",
  "adventures.status.done": "secondary",
  "adventures.status.inProgress": "primary",
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
  runId: string;
}

function AdventureRow({ adventure, numeral, statusKey, isCurrent, runId }: AdventureRowProps): ReactElement {
  const { t } = useTranslation("playthrough");
  const isLocked = statusKey === "adventures.status.locked";
  const isWaiting = statusKey === "adventures.status.waitingOnParty";
  const isInProgress = statusKey === "adventures.status.inProgress";

  // MUI's `Tooltip` sets `aria-label` to `title` whenever `title` is a
  // string (`Tooltip.js`: `titleIsString ? title : null`) -- so passing the
  // waiting sentence unconditionally and only suppressing the hover popup
  // via `disableHoverListener` still leaks that sentence into the ready
  // state's accessibility tree (verifier finding, live preview). `title`
  // must be non-string (`undefined`) outside the waiting state for MUI to
  // omit the label entirely, not just an empty string, which is still a
  // string and would set `aria-label=""`.
  const startButton = (
    <Tooltip title={isWaiting ? t("adventures.waitingHint") : undefined}>
      <span>
        <Button variant="outlined" size="small" disabled>
          {t("adventures.start")}
        </Button>
      </span>
    </Tooltip>
  );

  // The play screen itself is a sibling work item's route; this row only
  // ever links to its address (D12 decisions doc, "the play screen lives at
  // the run's address plus a play segment") -- it does not build the screen.
  const continueButton = (
    <Button variant="contained" size="small" component={RouterLink} to={`/runs/${runId}/play`}>
      {t("adventures.continue")}
    </Button>
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
          {isCurrent && !isInProgress && startButton}
          {isInProgress && continueButton}
          {isLocked && <Lock size={16} aria-hidden color="var(--text-muted)" />}
        </Box>
      </Stack>
    </Card>
  );
}

export function AdventuresSection({ adventures, members }: AdventuresSectionProps): ReactElement {
  const { t } = useTranslation("playthrough");
  // This component only ever renders under the `/runs/:runId` route
  // (`App.tsx`, via `RunRoute`), so the param is always present.
  const { runId } = useParams<"runId">();

  const partyReady = members.length > 0 && members.every((member) => member.ready);
  const currentIndex = adventures.findIndex((adventure) => adventure.status !== "done");
  // The heading's "waiting on party" hint only ever applies to a current
  // row that still needs starting -- an adventure already under way has
  // nothing left to be blocked on.
  const isBlocked = !partyReady && currentIndex !== -1 && adventures[currentIndex].status === "unplayed";

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
              : adventure.status === "active"
                ? "adventures.status.inProgress"
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
              runId={runId ?? ""}
            />
          );
        })}
      </Stack>
    </Stack>
  );
}
