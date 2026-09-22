// `/runs/:runId/create-character` (sprint 009-06, WI1, AC1-AC6). A reload
// remounts this route and starts a fresh conversation — nothing about it is
// stored in the browser (research.md Decision 1) — so `useBeforeUnload`
// (research.md fact 2: the one exit-warning hook that works without a data
// router; a plain listener re-exported off "react-router" itself, unlike
// `useBlocker`) is the only guard against losing it that way; the one
// in-app exit, "Back to the run", opens `LeaveDialog` instead of navigating
// directly (Decision 3). Browser Back is not intercepted, by the same fact.
import { useState } from "react";
import { useBeforeUnload, useNavigate, useParams } from "react-router";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import useMediaQuery from "@mui/material/useMediaQuery";
import { ChevronLeft } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useCreationChat } from "../hooks/useCreationChat";
import { Transcript } from "../components/Transcript";
import { Composer } from "../components/Composer";
import { OfferedChoices } from "../components/OfferedChoices";
import { SheetPanel } from "../components/SheetPanel";
import { LeaveDialog } from "../components/LeaveDialog";

export function CreationChatRoute() {
  // Only ever reached through `/runs/:runId/create-character`
  // (`App.tsx`), which guarantees the segment is present — same contract
  // `RunRoute` relies on for its own `runId`.
  const { runId } = useParams<"runId">();
  const { t } = useTranslation("character");
  const navigate = useNavigate();
  const theme = useTheme();
  const collapsed = useMediaQuery(theme.breakpoints.down("md"));
  const [leaveDialogOpen, setLeaveDialogOpen] = useState(false);

  const { turns, sheet, step, stepNumber, readyMadeName, isSending, failed, send, retry } = useCreationChat(runId!);

  useBeforeUnload(() => {
    // No return value needed for the app's own state — nothing here is
    // persisted either way — but returning a callback at all is what makes
    // the browser itself prompt on reload/close (research.md fact 2).
  });

  const hasPlayerTurn = turns.some((turn) => turn.speaker === "player");

  function handleLeave() {
    navigate(`/runs/${runId}`);
  }

  return (
    <Stack spacing={4}>
      <Button
        onClick={() => setLeaveDialogOpen(true)}
        startIcon={<ChevronLeft size={16} aria-hidden />}
        sx={{ alignSelf: "flex-start" }}
      >
        {t("chat.back")}
      </Button>

      <Stack spacing={1}>
        <Typography variant="h2" component="h1">
          {t("chat.title")}
        </Typography>
        <Typography sx={{ color: "text.secondary" }}>{t("chat.subtitle")}</Typography>
      </Stack>

      {collapsed && <SheetPanel sheet={sheet} stepNumber={stepNumber} collapsed />}

      <Box
        sx={{
          display: "grid",
          gap: 4,
          gridTemplateColumns: { xs: "1fr", md: "2fr 1fr" },
          alignItems: "start",
        }}
      >
        <Stack spacing={4}>
          <Transcript turns={turns} failed={failed} onRetry={retry} />
          <OfferedChoices
            step={step}
            stepNumber={stepNumber}
            readyMadeName={readyMadeName}
            hasPlayerTurn={hasPlayerTurn}
            onPick={send}
          />
          <Composer onSend={send} disabled={isSending} />
        </Stack>

        {!collapsed && <SheetPanel sheet={sheet} stepNumber={stepNumber} collapsed={false} />}
      </Box>

      <LeaveDialog open={leaveDialogOpen} onStay={() => setLeaveDialogOpen(false)} onLeave={handleLeave} />
    </Stack>
  );
}
