// One dashboard run card (sprint 007/07 WI1, AC1/AC2/AC4): a cover-art
// placeholder, the campaign title, the shared status badge (`runStatus.ts`),
// a teaser, the "Adventure n of m · k players · Created <relative>" line
// and a Begin/Resume action that opens the run screen
// (docs/design/dnd-app-dashboard-design/project/Dashboard.dc.html:41-63).
//
// A run whose pinned campaign content is gone (`unavailable: true`) renders
// muted with no open action at all — the "why" trigger below is a plain
// button that reveals an inline explanation on click and never navigates
// (decision, sprint brief: a plain muted card beats reusing
// `InDevelopmentDialog`, whose copy doesn't fit this reason).
import { useState, type ReactElement } from "react";
import { Link as RouterLink } from "react-router";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { RunSummary } from "../hooks/useRunSummaries";
import { runActionKey, runStatusKey } from "../runStatus";
import { formatRelativeDate } from "../relativeDate";

export interface CampaignCardProps {
  run: RunSummary;
}

function CoverArt(): ReactElement {
  const { t } = useTranslation("playthrough");

  return (
    <Box
      aria-hidden
      sx={(theme) => ({
        width: { xs: "100%", sm: 170 },
        height: { xs: 120, sm: 112 },
        flex: "0 0 auto",
        borderRadius: theme.shape.borderRadiusOrganicSoft,
        display: "grid",
        placeItems: "center",
        border: "1px solid var(--border-soft)",
        background: "linear-gradient(155deg, var(--loam-700), var(--bark-900) 60%, var(--loam-900))",
      })}
    >
      <Typography variant="overline" sx={{ color: "var(--text-faint)" }}>
        {t("dashboard.card.coverArtPlaceholder")}
      </Typography>
    </Box>
  );
}

function UnavailableCard(): ReactElement {
  const { t } = useTranslation("playthrough");
  const [explained, setExplained] = useState(false);

  return (
    <Card
      variant="outlined"
      sx={(theme) => ({
        borderRadius: theme.shape.borderRadiusOrganic,
        opacity: 0.6,
        backgroundColor: "var(--surface-inset)",
      })}
    >
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={4}
        sx={{ alignItems: { xs: "flex-start", sm: "center" }, p: 4 }}
      >
        <CoverArt />
        <Box sx={{ minWidth: 0, display: "grid", gap: 2, flex: 1 }}>
          <Typography sx={{ fontFamily: "var(--font-display)", fontWeight: "var(--weight-bold)", color: "var(--text-muted)" }}>
            {t("dashboard.card.unavailableTitle")}
          </Typography>
          <ButtonBase
            onClick={() => setExplained(true)}
            sx={(theme) => ({
              justifySelf: "start",
              borderRadius: theme.shape.borderRadiusOrganicSoft,
              px: 3,
              py: 1,
              color: "text.secondary",
              textDecoration: "underline",
            })}
          >
            {t("dashboard.card.unavailableTrigger")}
          </ButtonBase>
          {/* Not present until activated at all (rather than visually hidden
              via `Collapse`, which keeps its content mounted for the
              animation) — AC4 reads "on activation explains why", so the
              reason must be absent from the accessibility tree until then,
              not merely off-screen. */}
          {explained && (
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              {t("dashboard.card.unavailableReason")}
            </Typography>
          )}
        </Box>
      </Stack>
    </Card>
  );
}

export function CampaignCard({ run }: CampaignCardProps): ReactElement {
  const { t, i18n } = useTranslation("playthrough");

  if (run.unavailable) {
    return <UnavailableCard />;
  }

  // `unavailable: false` guarantees `campaignTitle`/`campaignSummary`/
  // `adventuresTotal` are the real values, not `null` (sprint brief's "API
  // facts") — the `?? 0` below only satisfies the wire type's nullability,
  // it never actually falls back in practice.
  const adventuresTotal = run.adventuresTotal ?? 0;
  const currentAdventure = Math.min(run.adventuresCompleted + 1, adventuresTotal);
  const statusKey = runStatusKey(run.status);
  const isArchived = statusKey === "run.status.archived";
  const actionKey = runActionKey(run.status);

  return (
    <Card
      variant="outlined"
      sx={(theme) => ({
        borderRadius: theme.shape.borderRadiusOrganic,
        ...(isArchived && { opacity: 0.6, backgroundColor: "var(--surface-inset)" }),
      })}
    >
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={4}
        sx={{ alignItems: { xs: "flex-start", sm: "center" }, p: 4 }}
      >
        <CoverArt />
        <Box sx={{ minWidth: 0, display: "grid", gap: 1, flex: 1 }}>
          <Stack direction="row" spacing={3} sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <Typography sx={{ fontFamily: "var(--font-display)", fontWeight: "var(--weight-bold)", fontSize: "1.1875rem" }}>
              {run.campaignTitle}
            </Typography>
            <Chip label={t(statusKey)} size="small" />
          </Stack>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            {run.campaignSummary}
          </Typography>
          <Typography variant="body2" sx={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)" }}>
            {t("dashboard.card.meta", {
              current: currentAdventure,
              total: adventuresTotal,
              players: t("dashboard.card.players", { count: run.playerCount }),
              date: formatRelativeDate(run.createdAt, i18n.language),
            })}
          </Typography>
        </Box>
        {actionKey !== null && (
          <Box
            sx={{
              flex: { xs: "1 1 100%", sm: "0 0 auto" },
              display: "flex",
              justifyContent: { xs: "flex-start", sm: "flex-end" },
            }}
          >
            <Button
              component={RouterLink}
              to={`/runs/${run.id}`}
              variant={actionKey === "dashboard.card.begin" ? "outlined" : "contained"}
              size="small"
            >
              {t(actionKey)}
            </Button>
          </Box>
        )}
      </Stack>
    </Card>
  );
}
