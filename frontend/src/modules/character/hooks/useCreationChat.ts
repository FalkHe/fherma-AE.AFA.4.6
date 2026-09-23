// The creation chat's whole client-side state (sprint 009-06, WI1,
// research.md Decision 5): two mutations — start on mount, send on every
// player turn — feeding one transcript kept in component state. There is no
// GET behind this conversation (it exists only as the sequence of replies),
// so holding it in `useState` is deliberate, not the "no server data in
// useState" default `frontend-stack.md` describes for everything else.
//
// `readyMadeName` is read straight off every reply (sprint 009-05's
// `CreationReply` plus the field WI0 adds this sprint) so `OfferedChoices`
// can offer the gate's "Take <name>" button without parsing it out of the
// greeting's prose.
//
// `canSave` (sprint 009-07, WI1, research.md Decision 1/6) lets the route
// gate `ReviewPanel` on `step === "review" && canSave`. A `saved: true`
// reply invalidates the run overview and navigates back to the run — the
// same invalidate-then-navigate shape `useStartCampaignRun` already uses,
// needed because the overview's 30s `staleTime` would otherwise show the
// stale, not-yet-ready party. An `error: true` reply still carries the
// server's current sheet and step. A failed save returns the previous draft,
// so the review stays visible (← AC5).
import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";

import { api } from "../../../core/api/client";
import { unwrap, type ApiFailure } from "../../../core/api/errors";
import type { components } from "../../../api/schema";

export type CreationReply = components["schemas"]["CreationReply"];
export type SheetSoFar = components["schemas"]["SheetSoFar"];
export type CreationStep = CreationReply["step"];

export interface ChatTurn {
  speaker: "keeper" | "player";
  text: string;
}

type CreationReplyResult = {
  data?: CreationReply;
  error?: components["schemas"]["ErrorEnvelope"];
  response: Response;
};

export function useCreationChat(runId: string) {
  const { t } = useTranslation("character");
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sheet, setSheet] = useState<SheetSoFar | null>(null);
  const [step, setStep] = useState<CreationStep | null>(null);
  const [stepNumber, setStepNumber] = useState(0);
  const [canSave, setCanSave] = useState(false);
  const [readyMadeName, setReadyMadeName] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const lastSentRef = useRef<string | null>(null);
  // Which `runId` the opening call has already gone out for. `main.tsx`
  // mounts the app in `StrictMode`, which in development runs every mount
  // effect twice (mount, simulated unmount, remount) while keeping the
  // component's refs — without this guard the start call fired twice and
  // the keeper's greeting landed in the transcript twice.
  const startedForRef = useRef<string | null>(null);

  function applyReply(reply: CreationReply) {
    setConversationId(reply.conversationId);
    setReadyMadeName(reply.readyMadeName ?? null);
    setFailed(reply.error);
    setTurns((previous) => [...previous, { speaker: "keeper", text: reply.reply }]);

    setSheet(reply.sheet);
    setStep(reply.step);
    setStepNumber(reply.stepNumber);
    setCanSave(reply.canSave);

    if (reply.saved) {
      void queryClient.invalidateQueries({ queryKey: ["runOverview", runId] });
      navigate(`/runs/${runId}`);
    }
  }

  function handleRequestFailure() {
    setFailed(true);
    setTurns((previous) => [...previous, { speaker: "keeper", text: t("chat.error") }]);
  }

  const startMutation = useMutation<CreationReply, ApiFailure, void>({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/character/runs/{run_id}/creation", {
          params: { path: { run_id: runId } },
        }) as unknown as Promise<CreationReplyResult>,
      ),
    onSuccess: applyReply,
    onError: handleRequestFailure,
  });

  const sendMutation = useMutation<CreationReply, ApiFailure, string>({
    mutationFn: (text) =>
      unwrap(
        api.POST("/api/v1/character/creation/{conversation_id}/messages", {
          params: { path: { conversation_id: conversationId! } },
          body: { text },
        }) as unknown as Promise<CreationReplyResult>,
      ),
    onSuccess: applyReply,
    onError: handleRequestFailure,
  });

  useEffect(() => {
    if (startedForRef.current === runId) {
      return;
    }
    startedForRef.current = runId;
    startMutation.mutate();
    // Runs once, on mount, for this `runId` — a reload remounts the route
    // and starts a fresh conversation (no browser-stored state, ← Decision
    // 1). The mutation object itself is stable across renders and would
    // otherwise never satisfy the exhaustive-deps rule as a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  function send(text: string) {
    lastSentRef.current = text;
    setFailed(false);
    setTurns((previous) => [...previous, { speaker: "player", text }]);
    sendMutation.mutate(text);
  }

  function retry() {
    setFailed(false);
    // The opening turn (no player text yet) retries the start call itself;
    // every later failure retries the player's last message without
    // duplicating its turn in the transcript.
    if (conversationId === null) {
      startMutation.mutate();
      return;
    }
    const lastText = lastSentRef.current;
    if (lastText === null) {
      return;
    }
    sendMutation.mutate(lastText);
  }

  return {
    turns,
    sheet,
    step,
    stepNumber,
    canSave,
    readyMadeName,
    isSending: sendMutation.isPending,
    failed,
    send,
    retry,
  };
}
