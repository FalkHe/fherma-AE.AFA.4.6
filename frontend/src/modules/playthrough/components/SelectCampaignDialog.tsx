// The "Select a campaign" dialog (sprint 007/09 WI1, AC1-AC5):
// docs/design/dnd-app-dashboard-design/project/Dashboard.dc.html:98-124
// (list layout, card treatment) and :203-226 (the picker dialog itself, the
// rolling-up inset row). Every campaign in the catalogue renders as one
// clickable card (placeholder art, title, teaser, adventure count — no tone
// badge, sprint brief's AC1); picking one starts the mutation and disables
// every card while it is in flight (AC2), an alert plus a retryable "Try
// again" replaces that row on failure without closing the dialog (AC4), and
// `onClose` resets the mutation so a stale error never survives into the
// next open (AC5).
import { useState, type ReactElement } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import { useCampaignCatalogue, type CampaignSummary } from "../hooks/useCampaignCatalogue";
import { useStartCampaignRun } from "../hooks/useStartCampaignRun";
import { CoverArt } from "./CoverArt";

export interface SelectCampaignDialogProps {
  open: boolean;
  onClose: () => void;
}

export function SelectCampaignDialog({ open, onClose }: SelectCampaignDialogProps): ReactElement {
  const { t } = useTranslation("playthrough");
  const { t: tCommon } = useTranslation("common");
  const { campaigns, isPending: catalogueIsPending, isError: catalogueIsError, retry: retryCatalogue } =
    useCampaignCatalogue();
  const mutation = useStartCampaignRun();
  const [pendingCampaign, setPendingCampaign] = useState<CampaignSummary | null>(null);

  function handleSelect(campaign: CampaignSummary) {
    setPendingCampaign(campaign);
    mutation.mutate(campaign.id);
  }

  function handleRetry() {
    if (pendingCampaign) {
      mutation.mutate(pendingCampaign.id);
    }
  }

  function handleClose() {
    mutation.reset();
    onClose();
  }

  // Reuse the sign-in form's mapping (sprint brief): the failure's own code
  // never reaches the player, only NETWORK vs. anything else.
  const errorMessage = mutation.isError
    ? mutation.error.code === "NETWORK"
      ? tCommon("errors.network")
      : tCommon("errors.unexpected")
    : null;

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="md">
      <DialogTitle>{t("dashboard.select.title")}</DialogTitle>
      <DialogContent>
        <Stack spacing={4}>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            {t("dashboard.select.intro")}
          </Typography>

          {catalogueIsPending && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
              <CircularProgress aria-label={tCommon("app.loading")} />
            </Box>
          )}

          {!catalogueIsPending && catalogueIsError && (
            <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
              <Alert severity="error">{tCommon("errors.network")}</Alert>
              <Button variant="outlined" onClick={retryCatalogue}>
                {tCommon("actions.retry")}
              </Button>
            </Stack>
          )}

          {!catalogueIsPending && !catalogueIsError && (
            <Box
              sx={{
                display: "grid",
                gap: 3,
                gridTemplateColumns: { xs: "1fr", sm: "repeat(auto-fit, minmax(240px, 1fr))" },
              }}
            >
              {campaigns.map((campaign) => (
                <ButtonBase
                  key={campaign.id}
                  onClick={() => handleSelect(campaign)}
                  disabled={mutation.isPending}
                  sx={(theme) => ({
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    borderRadius: theme.shape.borderRadiusOrganic,
                    overflow: "hidden",
                    border: "1px solid var(--border-soft)",
                    backgroundColor: "var(--surface-card)",
                  })}
                >
                  <CoverArt sx={{ width: "100%", height: 116 }} />
                  <Box sx={{ p: 3, display: "grid", gap: 1 }}>
                    <Typography sx={{ fontFamily: "var(--font-display)", fontWeight: "var(--weight-bold)" }}>
                      {campaign.title}
                    </Typography>
                    <Typography variant="body2" sx={{ color: "text.secondary" }}>
                      {campaign.summary}
                    </Typography>
                    <Typography variant="body2" sx={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)" }}>
                      {t("dashboard.select.adventureCount", { count: campaign.adventureCount })}
                    </Typography>
                  </Box>
                </ButtonBase>
              ))}
            </Box>
          )}

          {mutation.isPending && pendingCampaign && (
            <Stack
              direction="row"
              spacing={3}
              sx={(theme) => ({
                alignItems: "center",
                p: 3,
                borderRadius: theme.shape.borderRadiusOrganicSoft,
                backgroundColor: "var(--surface-inset)",
                border: "1px solid var(--border-hairline)",
              })}
            >
              <CircularProgress size={16} aria-hidden />
              <Typography variant="body2" sx={{ color: "text.secondary" }}>
                {t("dashboard.select.rollingUp", { title: pendingCampaign.title })}
              </Typography>
            </Stack>
          )}

          {mutation.isError && (
            <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
              <Alert severity="error">{errorMessage}</Alert>
              <Button variant="outlined" onClick={handleRetry}>
                {tCommon("actions.retry")}
              </Button>
            </Stack>
          )}
        </Stack>
      </DialogContent>
    </Dialog>
  );
}
