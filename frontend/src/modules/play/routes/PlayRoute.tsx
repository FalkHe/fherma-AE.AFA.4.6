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
// No party rail and no composer this sprint (sprint brief: "leave room for
// them per D12 but do not build them"). With neither built yet, D12's wide
// and narrow layouts (§2, §5) already coincide: one column, the header
// above the transcript, capped at the design's own chat column width.
import type { ReactElement } from "react";
import { Link as RouterLink, useParams } from "react-router";
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
import { Transcript } from "../components/Transcript";

interface PlayScreenProps {
  runId: string;
  table: PlayTable;
}

function PlayScreen({ runId, table }: PlayScreenProps): ReactElement {
  const { t } = useTranslation("play");
  // One hero per run (D9) — the transcript's own `player_action` payload
  // names no actor, so the caller supplies it from here (README.md
  // "Surface").
  const heroName = table.heroes[0]?.name ?? "";
  const { rows } = usePlayTranscript(runId, heroName);

  return (
    <Stack spacing={4} sx={{ maxWidth: "var(--width-chat)" }}>
      {/* `px: 4` matches `Transcript.tsx`'s own card padding (`p: 4`,
          `theme.spacing(4)` = the design system's `--sp-4` token) exactly —
          without it, the header's text sits flush against the page's own
          slim outer gutter while the card's text sits inset by its own
          padding, so the two visibly fail to line up at narrow widths (D12
          §5) even though their outer edges already coincide. */}
      <Stack spacing={1} sx={{ px: 4 }}>
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

      <Transcript rows={rows} />
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
