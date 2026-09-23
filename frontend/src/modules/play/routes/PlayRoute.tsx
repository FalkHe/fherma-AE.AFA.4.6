// `/runs/:runId/play` (sprint 010/06 WI4, D12 §2/§5, AC2/AC6/AC7): the
// Dungeon Master's table itself. Loading/error/not-found follow
// `RunRoute`'s own precedent (`modules/playthrough/routes/RunRoute.tsx`) —
// a labelled spinner, then an `Alert` with a retry button on an unexpected
// failure. The not-found line reuses `playthrough:run.notFound` ("This run
// could not be found.") rather than adding a new key: this screen's own
// namespace (`play.json`, I3) is already fixed to exactly D12's strings,
// and a run that plain does not exist is the same fact `RunRoute` already
// names — reading that key costs no file edit and no new wording.
//
// The header omits whichever of campaign/adventure/scene the table read
// answers `null` for (research.md Assumptions: "a run with no adventure
// yet ... omits those header lines"), rather than printing a blank line.
//
// `PlayScreen` below is a second component, not inlined here, so that
// `usePlayTranscript` — whose query key carries no hero name
// (`usePlayTranscript.ts`) — only ever mounts once `table` has resolved:
// calling it unconditionally at the top of `PlayRoute` itself would fire
// its first fetch with an empty hero name before the table read lands,
// and nothing would ever refetch it once the real name is known.
//
// No party rail yet (sprint brief: "leave room for it per D12 but do not
// build it"). The composer joins this sprint (010/07 WI6, I6), pinned below
// the transcript inside the same bounded-height `Stack` -- `flexShrink: 0`
// so it keeps its own height and the transcript above it keeps claiming the
// rest via `flex: "1 1 auto"`. With no party rail built yet, D12's wide and
// narrow layouts (§2, §5) still coincide: one column, the header above the
// transcript and the composer below it, capped at the design's own chat
// column width.
//
// The transcript is meant to be the thing that scrolls, not the page (D12
// §2: "the transcript keeps itself at the newest entry"). Every ancestor
// between the viewport and this screen — `AppShell`'s `<main>` and
// `Container` (`core/layout/AppShell.tsx`) — has an auto height, so a plain
// `height: "100%"` on the transcript resolves to nothing (verification
// round 1, defect 1: it never scrolled, the page did instead). Fixing that
// from here means giving *this* screen a genuine, viewport-relative height
// and letting the transcript fill whatever is left of it via flex, rather
// than reaching into `core/layout` (out of this work item's ownership).
import type { ReactElement } from "react";
import { Link as RouterLink, useParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import { usePlayTable, type PlayTable } from "../hooks/usePlayTable";
import { usePlayTranscript } from "../hooks/usePlayTranscript";
import { useRunNotices } from "../hooks/useRunNotices";
import { useTakeTurn } from "../hooks/useTakeTurn";
import { Transcript } from "../components/Transcript";
import { Composer, type ComposerState } from "../components/Composer";
import type { TranscriptRow } from "../transcript";

interface PlayScreenProps {
  runId: string;
  table: PlayTable;
}

// `AppShell`'s sticky `AppBar` (`core/layout/AppShell.tsx`) renders MUI's
// own default `Toolbar` minimum height — 56px below the `sm` breakpoint,
// 64px at `sm` and up — plus the 1px bottom border that component adds.
// Mirrored here, rather than read off `theme.mixins.toolbar` at render
// time, only to bound this screen's own height off the viewport; `AppShell`
// itself is `core/`, outside this work item.
const APP_BAR_HEIGHT_PX = { xs: 56 + 1, sm: 64 + 1 };

function PlayScreen({ runId, table }: PlayScreenProps): ReactElement {
  const { t } = useTranslation("play");
  const queryClient = useQueryClient();
  // One hero per run (D9) — the transcript's own `player_action` payload
  // names no actor, so the caller supplies it from here (README.md
  // "Surface").
  const heroName = table.heroes[0]?.name ?? "";
  const { rows, awaiting, turnUnfinished } = usePlayTranscript(runId, heroName);
  const { send, isSending, pending } = useTakeTurn({ runId, rows });

  // Live updates (sprint 010/07 WI6, I6 ← AC2): every `updated` notice off
  // the run's own stream just means "re-read the transcript" — the same
  // re-read a turn's own settle already triggers, so both paths share one
  // query key and one cache entry.
  useRunNotices(runId, () => {
    // `cancelRefetch` lives on `invalidateQueries`'s second argument, not
    // inside the filters object -- same note as `useTakeTurn.ts`'s own call.
    void queryClient.invalidateQueries({ queryKey: ["transcript", runId] }, { cancelRefetch: false });
  });

  // The player's own words show at once, before the network round-trip
  // that records them completes (AC1) — appended as a `player` row on top
  // of whatever the last transcript read holds, and dropped again the
  // moment `useTakeTurn` clears `pending` (its own echo has landed, or the
  // turn failed outright).
  const displayRows: TranscriptRow[] = pending
    ? [...rows, { kind: "player", id: "pending", author: heroName, text: pending.text, at: pending.at }]
    : rows;

  // A turn is still running whenever the mutation itself is in flight, or
  // -- after a reload mid-turn, when `useTakeTurn` holds nothing pending at
  // all -- whenever the last recorded event is not yet the closing
  // narration (AC4).
  const turnRunning = isSending || (awaiting === "none" && turnUnfinished);

  let composerState: ComposerState;
  if (awaiting.startsWith("roll:")) {
    composerState = "awaitingRoll";
  } else if (awaiting.startsWith("answer:")) {
    composerState = "awaitingChoice";
  } else {
    composerState = turnRunning ? "turnRunning" : "open";
  }

  return (
    <Stack
      spacing={4}
      sx={(theme) => {
        // The screen's own bounded height: the dynamic viewport height
        // minus the sticky `AppBar` above it and `AppShell`'s `Container`
        // padding (`py: 4`) around it — the only two ancestors with a
        // height that isn't itself content-driven. `minHeight: 0` lets the
        // `Transcript` child below claim the remainder through `flexGrow`
        // instead of the `Stack`'s own content pushing it taller than this.
        const containerPadding = `(${theme.spacing(4)} * 2)`;
        return {
          maxWidth: "var(--width-chat)",
          minHeight: 0,
          height: `calc(100dvh - ${APP_BAR_HEIGHT_PX.xs}px - ${containerPadding})`,
          [theme.breakpoints.up("sm")]: {
            height: `calc(100dvh - ${APP_BAR_HEIGHT_PX.sm}px - ${containerPadding})`,
          },
        };
      }}
    >
      {/* `px: 4` matches `Transcript.tsx`'s own card padding (`p: 4`,
          `theme.spacing(4)` = the design system's `--sp-4` token) exactly —
          without it, the header's text sits flush against the page's own
          slim outer gutter while the card's text sits inset by its own
          padding, so the two visibly fail to line up at narrow widths (D12
          §5) even though their outer edges already coincide. */}
      <Stack spacing={1} sx={{ px: 4, flexShrink: 0 }}>
        {table.campaignTitle !== null && (
          <Link component={RouterLink} to={`/runs/${runId}`} sx={{ alignSelf: "flex-start" }}>
            {t("header.back", { campaign: table.campaignTitle })}
          </Link>
        )}
        {table.adventure !== null && (
          <Typography variant="h2" component="h1">
            {table.adventure.title}
          </Typography>
        )}
        {table.scene !== null && (
          <Typography sx={{ color: "text.secondary" }}>{t("header.scene", { scene: table.scene.name })}</Typography>
        )}
      </Stack>

      <Box sx={{ flex: "1 1 auto", minHeight: 0 }}>
        <Transcript rows={displayRows} thinking={turnRunning} />
      </Box>

      <Box sx={{ px: 4, flexShrink: 0 }}>
        <Composer state={composerState} onSend={send} />
      </Box>
    </Stack>
  );
}

export function PlayRoute(): ReactElement {
  // Only ever reached through `/runs/:runId/play` (`App.tsx`), which
  // guarantees the segment is present — same contract `RunRoute` relies on
  // for its own `runId`.
  const { runId } = useParams<"runId">();
  const { t: tCommon } = useTranslation("common");
  const { t: tPlaythrough } = useTranslation("playthrough");
  const { table, isPending, isError, notFound, retry } = usePlayTable(runId!);

  if (isPending) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress aria-label={tCommon("app.loading")} />
      </Box>
    );
  }

  if (isError) {
    return (
      <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
        <Alert severity="error">{tCommon("errors.network")}</Alert>
        <Button variant="outlined" onClick={retry}>
          {tCommon("actions.retry")}
        </Button>
      </Stack>
    );
  }

  if (notFound || !table) {
    return <Typography>{tPlaythrough("run.notFound")}</Typography>;
  }

  return <PlayScreen runId={runId!} table={table} />;
}
