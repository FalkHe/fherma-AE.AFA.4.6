import { useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Icon from "@mui/material/Icon";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, useParams } from "react-router";

import { EmptyState } from "../components/EmptyState";
import { LiveConnectionAlert } from "../components/LiveConnectionAlert";
import { MessageBubble } from "../components/MessageBubble";
import { TypingIndicator } from "../components/TypingIndicator";
import {
  ChatError,
  useChatMessages,
  useSendMessage,
  type ChatMessage,
} from "../hooks/useChatMessages";
import { useChat } from "../hooks/useChats";
import { queryKeys } from "../queryKeys";

/**
 * One consultation: the conversation, the composer, and the derived state of the
 * current turn.
 *
 * There is no streaming and no polling anywhere in here. The rhythm is
 * `seen → typing… → completed message`, and the only live mechanism is the SSE
 * listener in the app shell dropping caches so the ordinary queries refetch.
 * Which means the whole turn state is *derived*, from two inputs only — the
 * timeline and the chat's `activeOperationId` (never `/api/operations`, which is
 * an admin endpoint) — so a page reloaded mid-reply resumes correctly with no
 * resume code path at all.
 */

/**
 * Server-side maximum length of a chat message, mirrored from
 * shared-knowledge. Over-length input is refused before it is sent.
 */
const MESSAGE_MAX_LENGTH = 4000;

/**
 * How long a turn may stay in flight before the UI calls it lost, mirroring the
 * backend's stale-pointer healing threshold (`AGENT_TIMEOUT_SECONDS + 30`) from
 * shared-knowledge. Keep the two in lockstep. Past it, the composer is re-enabled
 * and the next send heals the pointer server-side.
 */
const CHAT_TURN_STALE_SECONDS = 150;

/** How close to the bottom counts as "following the conversation" (ui-spec §5). */
const NEAR_BOTTOM_PX = 120;

/** Correlation id of an outgoing message; the server echoes it back. */
function nextLocalId(): string {
  return `local-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Whether the turn that started at `since` has been in flight too long.
 *
 * The flag is needed at page level (it decides both the timeline's fallback row
 * *and* whether the composer's send button is enabled), and it must flip without
 * anything happening on the network. So one timer, armed for the exact remaining
 * moment and re-armed whenever the reference timestamp changes; `null` (no turn
 * in flight) disarms it. The stale verdict is *derived* from the last tick rather
 * than stored as a boolean, which is what keeps a newer turn from inheriting an
 * older turn's staleness without a reset-in-effect.
 *
 * The tick is set to the `deadline`, **not** to `Date.now()`: Chromium fires a
 * long `setTimeout` a few milliseconds *early* (observed 9 ms short of a 150 s
 * timer), and with a `Date.now()` tick the strict comparison below then fails —
 * for good, because `deadline` never changes, so the effect never re-arms and the
 * turn stays "typing" forever. Recording the deadline makes the comparison mean
 * exactly what it should: *the timer for this deadline has fired*. A newer turn
 * still cannot inherit staleness, because its deadline is later than this tick.
 */
function useTurnIsStale(since: string | null): boolean {
  const [tick, setTick] = useState(() => Date.now());

  const deadline = since === null ? null : Date.parse(since) + CHAT_TURN_STALE_SECONDS * 1_000;

  useEffect(() => {
    if (deadline === null) {
      return;
    }

    const remaining = deadline - Date.now();

    if (remaining <= 0) {
      return;
    }

    const timer = window.setTimeout(() => setTick(deadline), remaining);

    return () => {
      window.clearTimeout(timer);
    };
  }, [deadline]);

  return deadline !== null && deadline <= tick;
}

export function ConsultationChatRoute() {
  const { t } = useTranslation();
  const { chatId = "" } = useParams();
  const queryClient = useQueryClient();

  const chat = useChat(chatId);
  const messages = useChatMessages(chatId);
  const send = useSendMessage(chatId);

  const [draft, setDraft] = useState("");

  const bottomRef = useRef<HTMLDivElement | null>(null);
  // Whether the viewport was at the bottom *before* the update that is about to
  // render: an arriving reply must not yank the page while history is being read.
  const wasNearBottomRef = useRef(true);
  const hasAnchoredRef = useRef(false);
  const hasJustSentRef = useRef(false);

  const rows = messages.data ?? [];
  const sendingRow = rows.find((row) => row.state === "sending");
  const failedRow = rows.find((row) => row.state === "failed");
  const lastRow = rows.at(-1);

  // Row 3 of ui-spec §3.3: the pointer is the truth, plus the short window
  // between a successful send and the chat detail's refetch.
  const turnInFlight =
    (chat.data?.activeOperationId ?? null) !== null ||
    (send.isSuccess && lastRow?.role === "user");

  const newestUserRow = rows.filter((row) => row.role === "user").at(-1);
  // The reference for staleness: the newest user message, or the chat itself for
  // the greeting turn, which has no user message yet.
  const turnSince = turnInFlight
    ? (newestUserRow?.createdAt ?? chat.data?.createdAt ?? null)
    : null;
  const isTurnStale = useTurnIsStale(turnSince);

  // First match wins: an unresolved send of our own outranks the advisor's turn.
  const showTurnState =
    turnInFlight && sendingRow === undefined && failedRow === undefined;

  const trimmedDraft = draft.trim();
  const isTooLong = draft.length > MESSAGE_MAX_LENGTH;
  // The composer stays *editable* while the advisor types — drafting the next
  // question is fine; only sending waits.
  const canSend =
    trimmedDraft !== "" &&
    !isTooLong &&
    !send.isPending &&
    sendingRow === undefined &&
    !(showTurnState && !isTurnStale);

  useEffect(() => {
    function handleScroll(): void {
      const distance =
        document.documentElement.scrollHeight - window.scrollY - window.innerHeight;

      wasNearBottomRef.current = distance <= NEAR_BOTTOM_PX;
    }

    window.addEventListener("scroll", handleScroll, { passive: true });

    return () => {
      window.removeEventListener("scroll", handleScroll);
    };
  }, []);

  // One string, so the effect runs exactly when the timeline's shape changes.
  const timelineSignature = `${rows.length}:${lastRow?.id ?? ""}:${String(showTurnState)}`;

  useEffect(() => {
    const anchor = bottomRef.current;

    if (anchor === null) {
      return;
    }

    // jsdom implements no scrolling at all; the optional call keeps the
    // behaviour out of the tests instead of stubbing the DOM.
    if (!hasAnchoredRef.current) {
      hasAnchoredRef.current = true;
      anchor.scrollIntoView?.({ behavior: "instant" });
      return;
    }

    if (hasJustSentRef.current) {
      hasJustSentRef.current = false;
      anchor.scrollIntoView?.({ behavior: "smooth" });
      return;
    }

    if (wasNearBottomRef.current) {
      anchor.scrollIntoView?.({ behavior: "smooth" });
    }
  }, [timelineSignature]);

  function submit(): void {
    if (!canSend) {
      return;
    }

    send.mutate({ body: trimmedDraft, localId: nextLocalId() });
    // The bubble holds the text from here on (a failed send keeps it), so the
    // composer is cleared immediately and focus stays where it is.
    setDraft("");
    hasJustSentRef.current = true;
    wasNearBottomRef.current = true;
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    // Enter sends, Shift+Enter inserts a newline, and an IME composing a
    // character owns the Enter key until it is done.
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) {
      return;
    }

    event.preventDefault();
    submit();
  }

  function retry(message: ChatMessage): void {
    if (message.localId === undefined) {
      return;
    }

    // Same `localId`: the entry flips back to "sending" in place.
    send.mutate({ body: message.body, localId: message.localId });
    hasJustSentRef.current = true;
  }

  function discard(message: ChatMessage): void {
    send.reset();
    queryClient.setQueryData<ChatMessage[]>(
      queryKeys.chatMessages.byChat(chatId),
      (cached) => cached?.filter((row) => row.localId !== message.localId),
    );
  }

  if (chat.isLoading || messages.isLoading) {
    return (
      <Box
        role="status"
        aria-label={t("common.loading")}
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "60vh",
        }}
      >
        <CircularProgress size={48} />
      </Box>
    );
  }

  const backToList = (
    <Button component={RouterLink} to="/consultations">
      {t("consultations.chat.back")}
    </Button>
  );

  if (chat.isError || chat.data === undefined || messages.isError) {
    const error = chat.isError ? chat.error : messages.error;
    const status = error instanceof ChatError ? error.status : 0;

    // The backend answers 404 both for an unknown chat and for somebody else's,
    // and so does this screen: no existence leak.
    if (status === 404) {
      return (
        <EmptyState
          icon="search_off"
          title={t("consultations.chat.notFoundTitle")}
          body={t("consultations.chat.notFoundBody")}
          action={backToList}
        />
      );
    }

    return (
      <EmptyState
        icon="error"
        title={t("consultations.chat.loadError")}
        body={t("common.errors.serverError")}
        action={
          <Button
            onClick={() => {
              void chat.refetch();
              void messages.refetch();
            }}
          >
            {t("common.retry")}
          </Button>
        }
      />
    );
  }

  const title =
    chat.data.title === null || chat.data.title === ""
      ? t("consultations.list.untitled")
      : chat.data.title;

  /** The caption under a bubble: `sending`/`failed` from the entry, `sent` from the turn. */
  function bubbleState(message: ChatMessage): ChatMessage["state"] {
    if (message.state !== undefined) {
      return message.state;
    }

    // "Seen" belongs to the turn, not to the row: the newest user message wears
    // it for as long as the advisor is working on the answer.
    return showTurnState && message === newestUserRow ? "sent" : undefined;
  }

  function renderTurnState() {
    if (!showTurnState) {
      return null;
    }

    if (isTurnStale) {
      return (
        <Stack
          direction="row"
          spacing={0.5}
          sx={{ alignItems: "center", justifyContent: "center", color: "error.main" }}
        >
          <Icon fontSize="inherit">error</Icon>
          <Typography variant="caption">
            {t("consultations.chat.turnFailed")}
          </Typography>
        </Stack>
      );
    }

    return <TypingIndicator />;
  }

  /**
   * Zero messages and no turn in flight: the rare case where the greeting itself
   * was lost. Not an `EmptyState` — the composer is the way out, so the intro is
   * a hint above it rather than a call to action of its own.
   */
  const isIdleAndEmpty = rows.length === 0 && !showTurnState;

  return (
    <>
      {/* `minWidth: 0` on the crumbs is load-bearing, not decoration: the title is
          the first user message truncated to 160 characters, and a flex item's
          automatic minimum size is its *min-content* width — which, under the
          spec's `noWrap`, is the whole untruncated line. Without this the crumb
          never shrinks and the document itself scrolls sideways on a phone
          (verified at 390 px), instead of the title ellipsizing. */}
      <Breadcrumbs sx={{ mb: 2, "& .MuiBreadcrumbs-li": { minWidth: 0 } }}>
        <Link component={RouterLink} to="/consultations">
          {t("consultations.chat.back")}
        </Link>
        <Typography color="text.primary" noWrap>
          {title}
        </Typography>
      </Breadcrumbs>
      <Box sx={{ maxWidth: 840, mx: "auto" }}>
        {isIdleAndEmpty ? (
          <Stack
            spacing={1}
            alignItems="center"
            sx={{ py: 6, textAlign: "center", color: "text.secondary" }}
          >
            <Icon sx={{ fontSize: 56 }}>two_wheeler</Icon>
            <Typography variant="h6" color="text.primary">
              {t("consultations.chat.introTitle")}
            </Typography>
            <Typography variant="body2" sx={{ maxWidth: 440 }}>
              {t("consultations.chat.introBody")}
            </Typography>
          </Stack>
        ) : (
          <Stack
            spacing={2}
            role="log"
            aria-label={t("consultations.chat.timelineLabel")}
          >
            {rows.map((message) => (
              <MessageBubble
                key={message.localId ?? message.id}
                message={message}
                state={bubbleState(message)}
                onRetry={message.state === "failed" ? () => retry(message) : undefined}
                onDiscard={
                  message.state === "failed" ? () => discard(message) : undefined
                }
              />
            ))}
            {renderTurnState()}
          </Stack>
        )}
        {/* The document itself scrolls — no nested scroll container, so the
            sticky composer sits above the on-screen keyboard on phones. */}
        <div ref={bottomRef} />
        {/* Somebody waiting for a reply must be told when the live connection is
            the reason nothing arrives. */}
        <LiveConnectionAlert />
        <Box
          component="form"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
          sx={{ position: "sticky", bottom: 0, py: 1.5, bgcolor: "background.default" }}
        >
          <Paper
            variant="outlined"
            sx={{ p: 1, display: "flex", alignItems: "flex-end", gap: 1 }}
          >
            <TextField
              multiline
              maxRows={6}
              fullWidth
              size="small"
              variant="outlined"
              autoFocus
              placeholder={t("consultations.chat.composerPlaceholder")}
              slotProps={{
                htmlInput: { "aria-label": t("consultations.chat.composerLabel") },
              }}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              error={isTooLong}
              helperText={isTooLong ? t("consultations.chat.messageTooLong") : undefined}
            />
            <IconButton
              type="submit"
              color="primary"
              aria-label={t("consultations.chat.send")}
              disabled={!canSend}
            >
              {send.isPending ? <CircularProgress size={24} /> : <Icon>send</Icon>}
            </IconButton>
          </Paper>
        </Box>
      </Box>
    </>
  );
}
