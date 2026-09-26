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
import { useEffect, useRef, type ReactElement } from "react";
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
import { useOpeningTurn } from "../hooks/useOpeningTurn";
import { useRunNotices } from "../hooks/useRunNotices";
import { useTakeTurn } from "../hooks/useTakeTurn";
import { Transcript } from "../components/Transcript";
import { Composer, type ComposerState } from "../components/Composer";
import { PendingPrompt } from "../components/PendingPrompt";
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
  // Fed to `usePlayTranscript`'s fallback poll below (sprint 010/07 WI7
  // round 2, ← AC2/AC4) -- a ref rather than `isSending` itself, since
  // `isSending` only exists once `useTakeTurn` has been called, and
  // `useTakeTurn` in turn needs this hook's own `rows` (`usePlayTranscript.ts`).
  const isSendingRef = useRef(false);
  // `pending` here is the transcript's own read of what the game is waiting
  // on (`PendingPrompt`, `transcript.ts`) -- not to be confused with
  // `useTakeTurn`'s own `pending`, the optimistic player row a turn just
  // sent (renamed `pendingTurn` below); the two are unrelated shapes that
  // happen to share a name across their own hooks.
  const { rows, awaiting, turnUnfinished, pending } = usePlayTranscript(runId, heroName, { isSendingRef });
  const { send, startOpening, roll, isSending, pending: pendingTurn } = useTakeTurn({ runId, rows });

  // Sprint 010/08 WI4, I5: a run just entered from the lobby carries
  // `{ startOpening: true }` in router state (`useEnterAdventure.ts`); this
  // fires the opening turn once and clears that state so a reload never
  // refires it (`useOpeningTurn.ts`). `isSending` already covers the
  // thinking line and the closed composer while it runs.
  useOpeningTurn(startOpening);

  // A ref, synced from its own effect (not read during render -- the
  // `react-hooks` lint rule disallows writing a ref's `.current` there,
  // and for good reason: React does not guarantee this render is the one
  // that commits). `usePlayTranscript.ts`'s own fallback-poll fix (defect A
  // round 2) no longer depends on this being perfectly up to the render;
  // the primary fix there is `useTakeTurn.ts`'s `cancelRefetch: true`, which
  // does not go through this ref at all.
  useEffect(() => {
    isSendingRef.current = isSending;
  }, [isSending]);

  // Live updates (sprint 010/07 WI6, I6 ← AC2): every `updated` notice off
  // the run's own stream just means "re-read the transcript" — the same
  // re-read a turn's own settle already triggers, so both paths share one
  // query key and one cache entry.
  useRunNotices(runId, () => {
    // `cancelRefetch` lives on `invalidateQueries`'s second argument, not
    // inside the filters object -- same note as `useTakeTurn.ts`'s own call.
    // `true` (defect A round 2, matching `useTakeTurn.ts`'s own fix): a tick
    // arriving while an earlier read from before this turn's narration
    // landed is still in flight must not fold into that stale read -- it
    // needs its own, fresh one, same reasoning as the post-turn settle.
    void queryClient.invalidateQueries({ queryKey: ["transcript", runId] }, { cancelRefetch: true });
  });

  // The player's own words show at once, before the network round-trip
  // that records them completes (AC1) — appended as a `player` row on top
  // of whatever the last transcript read holds, and dropped again the
  // moment `useTakeTurn` clears `pending` (its own echo has landed, or the
  // turn failed outright).
  const displayRows: TranscriptRow[] = pendingTurn
    ? [...rows, { kind: "player", id: "pending", author: heroName, text: pendingTurn.text, at: pendingTurn.at }]
    : rows;

  // A turn is still running whenever the mutation itself is in flight, or
  // -- after a reload mid-turn, when `useTakeTurn` holds nothing pending at
  // all -- whenever the last recorded event is not yet the closing
  // narration (AC4).
  const turnRunning = isSending || (awaiting === "none" && turnUnfinished);

  // Defect B fix: the table read (`usePlayTable.ts`) is fetched once on
  // mount and never invalidated by a turn settling, so `table.scene` itself
  // stays whatever scene the run was in when the page loaded -- a move
  // that enters a new scene mid-session left this line unchanged until a
  // reload. The transcript, by contrast, is already kept live (this turn's
  // own settle invalidates it, `useTakeTurn.ts`/`useRunNotices` above); its
  // own `scene_entered` rows (`divider`, `transcript.ts`) are the same fact
  // the header wants, read fresher. The *last* divider row in `rows` is the
  // scene most recently entered; `table.scene`'s own name is kept as the
  // fallback for a run with no scene row yet (a fresh adventure whose
  // opening turn has not landed one -- `table.scene` already reflects that
  // one correctly and the transcript would otherwise show nothing).
  const latestDivider = [...rows].reverse().find((row) => row.kind === "divider");
  const sceneName = latestDivider?.scene ?? table.scene?.name ?? null;

  // Sprint 010/09 WI5, I6: `isSending` wins outright -- the moment an answer
  // or a roll is sent, the buttons must be gone even before the transcript
  // re-read catches up and clears `awaiting` itself (the stale read still
  // names the same prompt for a moment, which would otherwise reopen the
  // buttons this render is meant to hide). Only once nothing is sending does
  // a still-open `awaiting` marker pick the choice/roll line; last, the
  // plain running/open split AC4 already covered.
  // The run itself is over (`finish_run`, `backend/app/modules/playthrough/
  // service.py`): `table.runStatus` flips to `"finished"` and stays there
  // for the rest of this run's life -- read straight off the table, not
  // derived from the transcript's own `ending` row, since a finished run
  // with a transcript the events read has not yet caught up to (a reload
  // racing the finishing turn's own settle) must close the composer just
  // as surely as one that has.
  const finished = table.runStatus === "finished";

  let composerState: ComposerState;
  if (isSending) {
    composerState = "turnRunning";
  } else if (awaiting.startsWith("roll:")) {
    composerState = "awaitingRoll";
  } else if (awaiting.startsWith("answer:")) {
    composerState = "awaitingChoice";
  } else if (turnRunning) {
    composerState = "turnRunning";
  } else {
    composerState = "open";
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
        {sceneName !== null && (
          <Typography sx={{ color: "text.secondary" }}>{t("header.scene", { scene: sceneName })}</Typography>
        )}
      </Stack>

      <Box sx={{ flex: "1 1 auto", minHeight: 0 }}>
        <Transcript
          rows={displayRows}
          thinking={turnRunning}
          prompt={
            pending !== null && !isSending ? (
              <PendingPrompt prompt={pending} onChoose={send} onRoll={roll} />
            ) : undefined
          }
        />
      </Box>

      <Box sx={{ px: 4, flexShrink: 0 }}>
        {finished ? (
          // A finished run never reopens for another turn (defect fix):
          // the composer's own three "closed" states (`Composer.tsx`) all
          // describe a turn still in progress, not a run that has ended
          // outright, so this is a fourth, permanent closed line, drawn
          // here rather than inside `Composer` since it alone needs the
          // campaign link back out.
          <Stack spacing={1} sx={{ alignItems: "center" }}>
            <Typography
              sx={{
                color: "text.secondary",
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-small)",
                textAlign: "center",
              }}
            >
              {t("composer.closed")}
            </Typography>
            {table.campaignTitle !== null && (
              <Link component={RouterLink} to={`/runs/${runId}`}>
                {t("end.button", { campaign: table.campaignTitle })}
              </Link>
            )}
          </Stack>
        ) : (
          <Composer state={composerState} onSend={send} />
        )}
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
