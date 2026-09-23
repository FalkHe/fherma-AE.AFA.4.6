// The conversation itself (sprint 009-06, WI1, AC2/AC5): one row per turn,
// labelled through `chat.keeper`/`chat.you` — the agent's on-screen name
// lives only in that locale value (D15), never in an identifier here. A
// failed turn (an `error: true` reply, already rendered as a keeper turn by
// `useCreationChat`, or a thrown request failure it renders in its place)
// adds one retry affordance below the transcript; the conversation itself
// never disappears (← AC5, D16 §1.17).
//
// Creation-chat viewport fix: the transcript is a sunken well that fills
// the space its page leaves it and scrolls on its own, keeping every turn.
// While the player sits within `STICK_THRESHOLD` of the bottom, new turns
// keep it pinned there; scrolling further up stops that and shows a "Jump
// to the latest" pill instead. A player send always re-pins. The pin is a
// plain `scrollTop = scrollHeight` in a layout effect — no
// `scrollIntoView` (jsdom lacks it); a guarded ResizeObserver re-pins when
// the well itself shrinks. Turns are chat bubbles after the design system's
// ChatMessage (`_ds_bundle.js`): the keeper's on the left in the display
// face over the lantern wash, the player's on the right on timber, each
// with its speaker label above it on the same side.
import { type ReactElement, useEffect, useLayoutEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { ChatTurn } from "../hooks/useCreationChat";

export interface TranscriptProps {
  turns: ChatTurn[];
  failed: boolean;
  onRetry: () => void;
}

/** How close to the bottom (px) still counts as "reading the latest". */
const STICK_THRESHOLD = 48;

function isNearBottom(el: HTMLElement): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= STICK_THRESHOLD;
}

export function Transcript({ turns, failed, onRetry }: TranscriptProps): ReactElement {
  const { t } = useTranslation("character");
  const { t: tCommon } = useTranslation("common");
  const scrollRef = useRef<HTMLDivElement>(null);
  // A ref, not state, for the layout effect: whether to pin is decided
  // against the scroll position the player left, not a re-render's.
  const stickRef = useRef(true);
  const [atBottom, setAtBottom] = useState(true);

  const lastIndex = turns.length - 1;
  const lastIsPlayer = turns[lastIndex]?.speaker === "player";

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el || !(stickRef.current || lastIsPlayer)) {
      return;
    }
    stickRef.current = true;
    // The browser answers this with a `scroll` event, which brings
    // `atBottom` back in line through `handleScroll`.
    el.scrollTop = el.scrollHeight;
  }, [turns, failed, lastIsPlayer]);

  // The well shrinks when a phone's keyboard opens (`interactive-widget=
  // resizes-content`) or the window is resized; a player reading the latest
  // turn stays pinned to it. Guarded because jsdom has no ResizeObserver.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(() => {
      if (stickRef.current) {
        el.scrollTop = el.scrollHeight;
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) {
      return;
    }
    const near = isNearBottom(el);
    stickRef.current = near;
    setAtBottom(near);
  }

  function jumpToLatest() {
    const el = scrollRef.current;
    if (!el) {
      return;
    }
    el.scrollTop = el.scrollHeight;
    stickRef.current = true;
    setAtBottom(true);
  }

  return (
    <Paper
      variant="outlined"
      sx={(theme) => ({
        position: "relative",
        display: "flex",
        flexDirection: "column",
        flex: 1,
        // A floor for the well on a wide screen only — a small phone with
        // the keyboard open must be free to shrink it further.
        minHeight: { xs: 0, md: 280 },
        bgcolor: "var(--surface-sunken)",
        borderRadius: theme.shape.borderRadiusOrganic,
        boxShadow: "none",
        overflow: "hidden",
      })}
    >
      <Box
        ref={scrollRef}
        role="log"
        aria-label={t("chat.transcript")}
        // Focusable so a keyboard user can scroll the log itself.
        tabIndex={0}
        onScroll={handleScroll}
        sx={{ flex: 1, minHeight: 0, overflowY: "auto", px: 7, py: 6 }}
      >
        <Stack spacing={5} component="ol" sx={{ m: 0, p: 0, listStyle: "none" }}>
          {turns.map((turn, index) => {
            const keeper = turn.speaker === "keeper";
            return (
              // The transcript only ever appends; nothing before an index is
              // ever reordered or removed, so the index is a stable key for
              // this list's whole lifetime.
              <Stack
                key={index}
                component="li"
                spacing={2}
                sx={{ alignItems: keeper ? "flex-start" : "flex-end" }}
              >
                <Typography
                  variant="overline"
                  sx={{ fontFamily: "var(--font-smallcaps)", color: "var(--text-muted)" }}
                >
                  {keeper ? t("chat.keeper") : t("chat.you")}
                </Typography>
                <Box
                  sx={(theme) => ({
                    py: 5,
                    px: 6,
                    boxShadow: theme.shadows[5],
                    ...(keeper
                      ? {
                          alignSelf: "flex-start",
                          maxWidth: "92%",
                          bgcolor: "var(--surface-card)",
                          border: "1px solid var(--border-soft)",
                          backgroundImage: "var(--wash-lantern)",
                          borderRadius: theme.shape.borderRadiusOrganic,
                        }
                      : {
                          alignSelf: "flex-end",
                          maxWidth: "80%",
                          bgcolor: "var(--surface-timber)",
                          border: "1px solid var(--border-timber)",
                          borderRadius: theme.shape.borderRadiusOrganicSoft,
                        }),
                  })}
                >
                  <Typography
                    role={failed && index === lastIndex ? "alert" : undefined}
                    sx={
                      keeper
                        ? { fontFamily: "var(--font-display)", fontSize: "var(--text-lead)", lineHeight: 1.55 }
                        : undefined
                    }
                  >
                    {turn.text}
                  </Typography>
                </Box>
              </Stack>
            );
          })}
        </Stack>
        {failed && (
          <Button variant="outlined" size="small" onClick={onRetry} sx={{ mt: 4 }}>
            {tCommon("actions.retry")}
          </Button>
        )}
      </Box>
      {!atBottom && (
        <Button
          variant="contained"
          size="small"
          onClick={jumpToLatest}
          sx={(theme) => ({
            position: "absolute",
            bottom: theme.spacing(4),
            left: "50%",
            transform: "translateX(-50%)",
            borderRadius: theme.shape.borderRadiusPill,
          })}
        >
          {t("chat.jumpToLatest")}
        </Button>
      )}
    </Paper>
  );
}
