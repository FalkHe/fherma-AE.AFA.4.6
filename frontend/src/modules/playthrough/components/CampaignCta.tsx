// The "Start a new campaign" card (sprint 007/07 WI1, AC1/AC3;
// sprint 007/09 WI1, AC1-AC6): docs/design/dnd-app-dashboard-design/project/
// Dashboard.dc.html:72-80. `prominent` only changes sizing: with no runs
// this card is the dashboard's one focal point (AC3); alongside a populated
// list it is a quieter footer instead.
//
// The button opens `SelectCampaignDialog`, whose open flag this card alone
// owns — same house pattern as `PartySection`'s `InDevelopmentDialog` (WI2):
// `DashboardRoute`'s two `CampaignCta` call sites are mutually exclusive
// branches (empty state vs. populated list), so per-instance state here
// never needs to be shared or lifted.
import { useState, type ReactElement } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";

import { SelectCampaignDialog } from "./SelectCampaignDialog";

export interface CampaignCtaProps {
  prominent?: boolean;
}

export function CampaignCta({ prominent = false }: CampaignCtaProps): ReactElement {
  const { t } = useTranslation("playthrough");
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <Card
      variant="outlined"
      sx={(theme) => ({
        borderRadius: theme.shape.borderRadiusOrganic,
        backgroundColor: "var(--surface-timber)",
        borderColor: "var(--border-timber)",
        p: prominent ? 8 : 5,
      })}
    >
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={4}
        sx={{ alignItems: { xs: "stretch", sm: "center" }, justifyContent: "space-between" }}
      >
        <Box sx={{ minWidth: 0, display: "grid", gap: 1 }}>
          <Typography
            variant={prominent ? "h4" : "h6"}
            component="p"
            sx={{ fontFamily: "var(--font-display)", fontWeight: "var(--weight-bold)" }}
          >
            {t("dashboard.cta.title")}
          </Typography>
          <Typography sx={{ color: "text.secondary" }}>{t("dashboard.cta.body")}</Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<Plus size={16} aria-hidden />}
          onClick={() => setDialogOpen(true)}
          sx={{ flex: "0 0 auto" }}
        >
          {t("dashboard.cta.button")}
        </Button>
      </Stack>
      <SelectCampaignDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />
    </Card>
  );
}
