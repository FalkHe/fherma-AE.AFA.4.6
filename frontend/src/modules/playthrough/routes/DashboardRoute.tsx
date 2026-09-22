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
import { useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import { useCurrentUser } from "../../auth/hooks/useCurrentUser";
import { useRunSummaries } from "../hooks/useRunSummaries";
import { CampaignCard } from "../components/CampaignCard";
import { CampaignCta } from "../components/CampaignCta";
import { runStatusKey, type RunStatusKey } from "../runStatus";

// Fixed tag order (sprint 007/08 WI1, AC1/AC4): "In progress" first because
// it is the opening tag whenever anything qualifies, then "New", then
// "Archived" last as the least-active state. The tag set IS `RunStatusKey`
// (sprint brief) — reusing it keeps a card's badge and its tag structurally
// unable to disagree.
const TAGS: RunStatusKey[] = ["run.status.inProgress", "run.status.new", "run.status.archived"];

export function DashboardRoute() {
  const { t } = useTranslation("playthrough");
  const { t: tCommon } = useTranslation("common");
  const { user } = useCurrentUser();
  const { runs, isPending, isError, retry } = useRunSummaries();
  const greetingRef = useRef<HTMLHeadingElement>(null);

  // AC5: only the player's own choice is state; the opening tag is derived
  // fresh every render from the runs already on hand, so no effect fires
  // when the query settles and there is no wrong-tag flash (sprint brief).
  const [picked, setPicked] = useState<RunStatusKey | null>(null);
  const defaultTag: RunStatusKey = runs.some((run) => runStatusKey(run.status) === "run.status.inProgress")
    ? "run.status.inProgress"
    : "run.status.new";
  const activeTag = picked ?? defaultTag;
  const visibleRuns = runs.filter((run) => runStatusKey(run.status) === activeTag);

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
          <Stack spacing={4}>
            <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 3 }}>
              <Typography
                variant="overline"
                sx={{ fontFamily: "var(--font-display)", letterSpacing: "0.14em", color: "var(--text-faint)" }}
              >
                {t("dashboard.tags.heading")}
              </Typography>
              <ToggleButtonGroup
                value={activeTag}
                exclusive
                onChange={(_event, next: RunStatusKey | null) => {
                  // MUI emits `null` when the pressed button is re-clicked
                  // (gotcha above) — ignored so a player can never deselect
                  // into an empty state.
                  if (next !== null) {
                    setPicked(next);
                  }
                }}
                aria-label={t("dashboard.tags.groupLabel")}
              >
                {TAGS.map((tag) => (
                  <ToggleButton key={tag} value={tag}>
                    {t(tag)}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
            </Stack>

            {activeTag === "run.status.archived" && (
              <Typography variant="body2" sx={{ color: "text.secondary" }}>
                {t("dashboard.tags.archivedNote")}
              </Typography>
            )}

            {visibleRuns.length === 0 ? (
              <Typography sx={{ color: "text.secondary" }}>{t("dashboard.tags.empty")}</Typography>
            ) : (
              <Stack spacing={3}>
                {visibleRuns.map((run) => (
                  <CampaignCard key={run.id} run={run} />
                ))}
              </Stack>
            )}
          </Stack>
          <CampaignCta />
        </>
      )}
    </Stack>
  );
}
