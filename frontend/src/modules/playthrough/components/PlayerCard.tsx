// One seat in the party grid (sprint 007/05 WI2, AC2/AC3) — initial, name,
// role badge, character state and a "Create character" link that always
// opens the creation chat at `createHref` (sprint 009/06 WI1, AC1: the
// creation flow now exists, so the button reads the same whether or not the
// member already has a character — brief's own wording lists it as a fixed
// per-card element, not conditional on readiness — but navigates instead of
// opening the in-development dialog). Visual treatment (card tone,
// state-box fill) still tracks `ready` so a party that already has its
// characters reads differently from one that doesn't
// (docs/design/dnd-app-dashboard-design/project/CampaignRun.dc.html:39-59).
import type { ReactElement } from "react";
import { Link as RouterLink } from "react-router";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Feather, Shield } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { RunMember } from "../hooks/useRunOverview";

export interface PlayerCardProps {
  member: RunMember;
  createHref: string;
}

export function PlayerCard({ member, createHref }: PlayerCardProps): ReactElement {
  const { t } = useTranslation("playthrough");
  const initial = member.username.charAt(0).toUpperCase();

  return (
    <Card
      variant="outlined"
      sx={(theme) => ({
        borderRadius: theme.shape.borderRadiusOrganic,
        backgroundColor: member.ready ? theme.palette.background.paper : "var(--surface-sunken)",
      })}
    >
      <CardContent sx={{ display: "grid", gap: 4 }}>
        <Stack direction="row" spacing={4} sx={{ alignItems: "center", minWidth: 0 }}>
          <Avatar
            sx={(theme) => ({
              bgcolor: "var(--surface-timber)",
              border: "1px solid var(--border-timber)",
              color: theme.palette.text.primary,
              fontFamily: "var(--font-smallcaps)",
            })}
          >
            {initial}
          </Avatar>
          <Box sx={{ minWidth: 0, display: "grid", gap: 1 }}>
            <Stack direction="row" spacing={3} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <Typography sx={{ fontFamily: "var(--font-display)", fontWeight: "var(--weight-bold)" }}>
                {member.username}
              </Typography>
              <Chip
                label={t(`party.roles.${member.role}`, { defaultValue: member.role })}
                size="small"
                color={member.role === "owner" ? "primary" : "default"}
              />
            </Stack>
          </Box>
        </Stack>

        <Box
          sx={(theme) => ({
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 4,
            flexWrap: "wrap",
            p: 4,
            borderRadius: theme.shape.borderRadiusOrganicSoft,
            backgroundColor: member.ready ? "var(--accent-secondary-quiet)" : "var(--surface-inset)",
            border: `1px solid ${member.ready ? "var(--accent-secondary)" : "var(--border-hairline)"}`,
          })}
        >
          <Stack direction="row" spacing={3} sx={{ alignItems: "center", minWidth: 0 }}>
            {member.ready ? (
              <Shield size={16} aria-hidden color="var(--moss-300)" />
            ) : (
              <Feather size={16} aria-hidden color="var(--text-muted)" />
            )}
            <Typography variant="body2" noWrap>
              {member.characterName ?? t("party.card.noCharacter")}
            </Typography>
          </Stack>
          <Button variant="outlined" size="small" component={RouterLink} to={createHref}>
            {t("party.card.createCharacter")}
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}
