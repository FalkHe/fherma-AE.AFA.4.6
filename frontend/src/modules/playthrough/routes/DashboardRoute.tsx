// The signed-in landing address, `/` (sprint 007/07 WI1, AC1-AC6): a
// greeting plus one card per run the player belongs to, newest first
// (server order, never re-sorted), or the invitation card alone when there
// are none (docs/design/dnd-app-dashboard-design/project/Dashboard.dc.html:
// 36-97). Replaces `modules/home`'s `HomeRoute` entirely.
//
// The greeting is the page's one `<h1>` and the post-sign-in focus target
// (same contract `HomeRoute` carried — SignInRoute.test.tsx's UI-12), so it
// renders from `useCurrentUser` alone, independently of `useRunSummaries`'s
// own pending/error state: a slow or failed runs read must never blank out
// or delay the heading a screen reader user has already been sent to.
import { useEffect, useRef } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import { useCurrentUser } from "../../auth/hooks/useCurrentUser";
import { useRunSummaries } from "../hooks/useRunSummaries";
import { CampaignCard } from "../components/CampaignCard";
import { CampaignCta } from "../components/CampaignCta";

export function DashboardRoute() {
  const { t } = useTranslation("playthrough");
  const { t: tCommon } = useTranslation("common");
  const { user } = useCurrentUser();
  const { runs, isPending, isError, retry } = useRunSummaries();
  const greetingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    document.title = tCommon("app.title");
  }, [tCommon]);

  // Focus once, on arrival — same contract as the retired `HomeRoute`
  // (ui-spec.md §6.5), not re-run when the runs query later settles.
  useEffect(() => {
    greetingRef.current?.focus();
  }, []);

  const hasRuns = runs.length > 0;

  return (
    <Stack spacing={6}>
      <Typography variant="h2" component="h1" tabIndex={-1} ref={greetingRef}>
        {t("dashboard.greeting", { username: user?.username ?? "" })}
      </Typography>

      {!isPending && !isError && hasRuns && (
        <Typography sx={{ color: "text.secondary" }}>
          {t("dashboard.subtitle", { count: runs.length })}
        </Typography>
      )}

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

      {!isPending && !isError && !hasRuns && <CampaignCta prominent />}

      {!isPending && !isError && hasRuns && (
        <>
          <Stack spacing={3}>
            {runs.map((run) => (
              <CampaignCard key={run.id} run={run} />
            ))}
          </Stack>
          <CampaignCta />
        </>
      )}
    </Stack>
  );
}
