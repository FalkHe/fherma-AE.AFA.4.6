// `/runs/:runId/create-character` (sprint 009-06, WI1, AC1-AC6; sprint
// 009-07, WI1, AC1/AC2/AC5). A reload remounts this route and starts a fresh
// conversation — nothing about it is stored in the browser (research.md
// Decision 1) — so `useBeforeUnload` (research.md fact 2: the one
// exit-warning hook that works without a data router; a plain listener
// re-exported off "react-router" itself, unlike `useBlocker`) is the only
// guard against losing it that way; the one in-app exit, "Back to the run",
// opens `LeaveDialog` instead of navigating directly (Decision 3). Browser
// Back is not intercepted, by the same fact.
//
// `ReviewPanel` replaces `Transcript`/`OfferedChoices` once
// `step === "review" && canSave` (sprint 009-07 research.md Decision 1) —
// the composer stays either way. "Change something" (Decision 2) dismisses
// the review until the player picks "Review and save" in the dock: the
// backend stays at `review`/`canSave` for the whole change round, so any
// automatic re-open (the earlier "two player turns" rule) covered the
// keeper's answer the moment it landed.
//
// Creation-chat viewport fix: the page marks itself `data-fit-viewport`, so
// `AppShell` caps it at the viewport. The header, the narrow-screen sheet
// strip (hidden during the review) and the dock (offered choices above the
// composer) never scroll; the transcript well — or `ReviewPanel` in its
// place — takes the remaining height and scrolls inside, and on a wide
// screen the sheet card sits in its own rail, scrolling on its own too.
// While the review shows, the rail is dropped and the review takes the full
// width — it is the whole sheet already.
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
import { ReviewPanel } from "../components/ReviewPanel";
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
  const [reviewDismissed, setReviewDismissed] = useState(false);

  const { turns, sheet, step, stepNumber, canSave, readyMadeName, isSending, failed, send, retry } =
    useCreationChat(runId!);

  useBeforeUnload(() => {
    // No return value needed for the app's own state — nothing here is
    // persisted either way — but returning a callback at all is what makes
    // the browser itself prompt on reload/close (research.md fact 2).
  });

  const hasPlayerTurn = turns.some((turn) => turn.speaker === "player");

  // A change that sends the conversation back to an earlier step (say, a
  // new class) ends the dismissal, so arriving at the review again opens it
  // on its own — React's "adjust state while rendering" pattern.
  if (reviewDismissed && step !== "review") {
    setReviewDismissed(false);
  }
  const reviewReady = step === "review" && canSave;
  const showReview = reviewReady && !reviewDismissed;
  const reviewing = showReview && sheet !== null;

  function handleLeave() {
    navigate(`/runs/${runId}`);
  }

  // A picked choice leaves the buttons it came from behind (the step moves
  // on), so focus goes to the composer instead of dropping to the page —
  // except on a touch screen, where focusing the field would pop the
  // on-screen keyboard over the reply the player is about to read.
  function handlePick(text: string) {
    send(text);
    const coarse = typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;
    if (!coarse) {
      document.getElementById("creation-chat-composer")?.focus();
    }
  }

  function handleSave() {
    send(t("review.save"));
  }

  function handleChangeSomething() {
    setReviewDismissed(true);
    send(t("review.change"));
  }

  return (
    <Box
      // Opts this page into `AppShell`'s viewport fit (creation-chat
      // viewport fix): the page itself never scrolls, only the well does.
      data-fit-viewport=""
      sx={{ flex: "1 1 0", minHeight: 0, display: "flex", flexDirection: "column" }}
    >
      <Stack
        direction={{ xs: "row", md: "column" }}
        spacing={3}
        sx={{ alignItems: { xs: "center", md: "flex-start" }, mb: 5, flexShrink: 0 }}
      >
        <Button
          onClick={() => setLeaveDialogOpen(true)}
          startIcon={<ChevronLeft size={16} aria-hidden />}
          sx={{ flexShrink: 0 }}
        >
          {t("chat.back")}
        </Button>

        <Stack spacing={1} sx={{ minWidth: 0 }}>
          <Typography variant="h2" component="h1" sx={{ typography: { xs: "h4", md: "h2" } }}>
            {t("chat.title")}
          </Typography>
          {/* Hidden by CSS, not unmounted, below `md`: the header must stay
              one short row there, but the copy stays in the DOM. */}
          <Typography sx={{ color: "text.secondary", display: { xs: "none", md: "block" } }}>
            {t("chat.subtitle")}
          </Typography>
        </Stack>
      </Stack>

      {collapsed && !showReview && (
        <Box sx={{ flexShrink: 0, mb: 5 }}>
          <SheetPanel sheet={sheet} stepNumber={stepNumber} collapsed />
        </Box>
      )}

      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          display: "grid",
          // The review is itself the full sheet, so it takes the whole width
          // and the rail beside it is dropped.
          gridTemplateColumns: reviewing
            ? "minmax(0, 1fr)"
            : { xs: "minmax(0, 1fr)", md: "minmax(0, 1fr) var(--width-rail)" },
          gridTemplateRows: "minmax(0, 1fr)",
          gap: 7,
        }}
      >
        <Stack spacing={4} sx={{ minHeight: 0 }}>
          {reviewing ? (
            <ReviewPanel sheet={sheet} failed={failed} errorText={t("chat.error")} onSave={handleSave} onChange={handleChangeSomething} />
          ) : (
            <Transcript turns={turns} failed={failed} onRetry={retry} />
          )}
          <Stack spacing={3} sx={{ flexShrink: 0 }}>
            {!reviewing && (
              <OfferedChoices
                step={step}
                stepNumber={stepNumber}
                readyMadeName={readyMadeName}
                hasPlayerTurn={hasPlayerTurn}
                onPick={handlePick}
              />
            )}
            {/* A view switch, not a message: the sheet is already savable,
                so going back to it sends nothing. */}
            {reviewReady && reviewDismissed && (
              <Button
                variant="contained"
                onClick={() => setReviewDismissed(false)}
                disabled={isSending}
                sx={{ alignSelf: "flex-start" }}
              >
                {t("review.back")}
              </Button>
            )}
            <Composer onSend={send} disabled={isSending} />
          </Stack>
        </Stack>

        {!collapsed && !reviewing && (
          <Box sx={{ minHeight: 0, display: "flex", flexDirection: "column" }}>
            <SheetPanel sheet={sheet} stepNumber={stepNumber} collapsed={false} />
          </Box>
        )}
      </Box>

      <LeaveDialog open={leaveDialogOpen} onStay={() => setLeaveDialogOpen(false)} onLeave={handleLeave} />
    </Box>
  );
}
