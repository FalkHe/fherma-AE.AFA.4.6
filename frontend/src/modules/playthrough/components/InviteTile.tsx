// The dashed "add a seat" placeholder alongside the party cards (sprint
// 007/05 WI2, AC3) — a real button (not a disabled affordance) that opens
// the same in-development dialog every "Create character" button opens,
// matching the design's dashed/placeholder card treatment
// (docs/design/dnd-app-dashboard-design/project/CampaignRun.dc.html:64-68).
import type { ReactElement } from "react";
import ButtonBase from "@mui/material/ButtonBase";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";

export interface InviteTileProps {
  onInvite: () => void;
}

export function InviteTile({ onInvite }: InviteTileProps): ReactElement {
  const { t } = useTranslation("playthrough");

  return (
    <ButtonBase
      onClick={onInvite}
      sx={(theme) => ({
        minHeight: 150,
        borderRadius: theme.shape.borderRadiusOrganic,
        border: "1px dashed var(--border-strong)",
        transition: `border-color ${theme.transitions.duration.standard}ms ${theme.transitions.easing.easeInOut}`,
        "&:hover": {
          backgroundColor: theme.palette.action.hover,
          borderColor: "var(--accent-hover)",
        },
      })}
    >
      <Stack spacing={2} sx={{ alignItems: "center", justifyContent: "center", py: 2 }}>
        <Plus size={20} aria-hidden color="var(--accent)" />
        <Typography sx={{ color: "text.primary" }}>{t("party.invite.title")}</Typography>
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          {t("party.invite.subtitle")}
        </Typography>
      </Stack>
    </ButtonBase>
  );
}
