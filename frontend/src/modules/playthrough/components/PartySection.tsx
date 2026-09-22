// The run screen's party grid (sprint 007/05 WI2, AC2/AC3): a "n of m
// characters ready" readout, one `PlayerCard` per seated member and an
// `InviteTile` for the empty seats still open. The invite tile still opens
// the shared in-development dialog this component owns; "Create character"
// no longer does (sprint 009/06 WI1, AC1) — it is now a plain link to its
// own page, built from `runId`.
import { useState, type ReactElement } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { RunMember } from "../hooks/useRunOverview";
import { InDevelopmentDialog } from "./InDevelopmentDialog";
import { PlayerCard } from "./PlayerCard";
import { InviteTile } from "./InviteTile";

export interface PartySectionProps {
  runId: string;
  members: RunMember[];
}

export function PartySection({ runId, members }: PartySectionProps): ReactElement {
  const { t } = useTranslation("playthrough");
  const [dialogOpen, setDialogOpen] = useState(false);

  const readyCount = members.filter((member) => member.ready).length;

  return (
    <Stack spacing={4} component="section">
      <Stack direction="row" spacing={4} sx={{ alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
        <Typography variant="overline" sx={{ color: "text.secondary" }}>
          {t("party.heading")}
        </Typography>
        <Typography variant="body2" sx={{ color: "text.disabled", fontFamily: "var(--font-mono)" }}>
          {t("party.readyLabel", { ready: readyCount, total: members.length })}
        </Typography>
      </Stack>

      <Box
        sx={{
          display: "grid",
          gap: 4,
          gridTemplateColumns: { xs: "1fr", sm: "repeat(auto-fit, minmax(300px, 1fr))" },
          alignItems: "start",
        }}
      >
        {members.map((member) => (
          <PlayerCard key={member.userId} member={member} createHref={`/runs/${runId}/create-character`} />
        ))}
        <InviteTile onInvite={() => setDialogOpen(true)} />
      </Box>

      <InDevelopmentDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />
    </Stack>
  );
}
