// `/runs/:runId` (sprint 007/05 WI1, AC1/AC5) — the campaign header (badge,
// title, description) from one `useRunOverview` read, plus the party section
// WI2 owns. Loading/error/retry follow `RequireAuth`'s own precedent
// (modules/auth/components/RequireAuth.tsx:42-61): a labelled spinner, then
// an `Alert` with a retry button on an unexpected failure. A 404 and an
// `unavailable: true` 200 both read as the same plain not-found message
// (decision, sprint brief) — `useRunOverview` already folds them into one
// `notFound` flag, so this component only ever branches on it once.
import { useEffect } from "react";
import { Link as RouterLink, useParams } from "react-router";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { ChevronLeft } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useRunOverview } from "../hooks/useRunOverview";
import { PartySection } from "../components/PartySection";

// D11's dashboard vocabulary, reused here so both screens speak of a run the
// same way (decision handed down for this work item): `setup` reads "New";
// `ready`/`active` read "In progress"; `archived`/`finished` read
// "Archived". `status` comes off the wire as a plain `string` (schema.d.ts),
// not a literal union, so an unrecognised value falls back to "New" rather
// than rendering nothing.
type StatusKey = "run.status.new" | "run.status.inProgress" | "run.status.archived";

function statusKey(status: string): StatusKey {
  switch (status) {
    case "ready":
    case "active":
      return "run.status.inProgress";
    case "archived":
    case "finished":
      return "run.status.archived";
    default:
      return "run.status.new";
  }
}

export function RunRoute() {
  // `useParams`'s value type is `string | undefined` regardless of the key
  // generic (`Params<Key>`, react-router) — but this component is only ever
  // reached through the `/runs/:runId` route registered in `App.tsx`, which
  // guarantees the segment is present.
  const { runId } = useParams<"runId">();
  const { t } = useTranslation("playthrough");
  const { t: tCommon } = useTranslation("common");
  const { overview, isPending, isError, notFound, retry } = useRunOverview(runId!);

  useEffect(() => {
    document.title = overview ? `${overview.campaignTitle} · ${tCommon("app.title")}` : tCommon("app.title");
  }, [overview, tCommon]);

  return (
    <Stack spacing={4}>
      <Link
        component={RouterLink}
        to="/"
        sx={{ display: "inline-flex", alignItems: "center", gap: 1, alignSelf: "flex-start" }}
      >
        <ChevronLeft size={16} aria-hidden />
        {t("run.back")}
      </Link>

      {isPending && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
          <CircularProgress aria-label={tCommon("app.loading")} />
        </Box>
      )}

      {!isPending && isError && (
        <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
          <Alert severity="error">{tCommon("errors.network")}</Alert>
          <Button variant="outlined" onClick={retry}>
            {tCommon("actions.retry")}
          </Button>
        </Stack>
      )}

      {!isPending && !isError && notFound && <Typography>{t("run.notFound")}</Typography>}

      {!isPending && !isError && !notFound && overview && (
        <>
          <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
            <Chip label={t(statusKey(overview.status))} size="small" />
            <Typography variant="h2" component="h1">
              {overview.campaignTitle}
            </Typography>
            <Typography sx={{ color: "text.secondary", maxWidth: "var(--width-prose)" }}>
              {overview.campaignSummary}
            </Typography>
          </Stack>

          <PartySection members={overview.members} />
        </>
      )}
    </Stack>
  );
}
