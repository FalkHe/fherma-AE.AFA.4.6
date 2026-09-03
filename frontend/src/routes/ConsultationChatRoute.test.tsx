import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "../api/schema";
import { jsonResponse, stubFetch } from "../test/network";
import { renderWithProviders } from "../test/render";

import { ConsultationChatRoute } from "./ConsultationChatRoute";

/**
 * The conversation state machine of ui-spec §3.3, row by row, plus the composer's
 * keyboard contract — all against a small in-memory `chats`/`chat-messages` API
 * behind the `fetch` stub, so the real request path (envelope unwrapping, page
 * walk, error mapping, the optimistic update) is what the assertions exercise.
 *
 * The chat id normally comes from the path; the route is rendered on its own here
 * (the app's route table is not under test), so `useParams` is doubled.
 */

type ChatResource = components["schemas"]["ChatResource"];
type ChatMessageResource = components["schemas"]["ChatMessageResource"];

const CHAT_IDS = {
  interview: "01CHATINTERVIEW00000000001",
  typing: "01CHATTYPING000000000000001",
  stale: "01CHATSTALE0000000000000001",
  flip: "01CHATFLIP00000000000000001",
  new: "01CHATNEW000000000000000001",
  empty: "01CHATEMPTY0000000000000001",
  gone: "01CHATGONE00000000000000001",
} as const;

/** Bodies the fake API answers with a failure, so both paths are reachable. */
const FAILING_BODY = "fail";
const CONFLICTING_BODY = "busy";

let chatIdParam: string = CHAT_IDS.interview;

vi.mock("react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>();

  return { ...actual, useParams: () => ({ chatId: chatIdParam }) };
});

function minutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

/** `CHAT_TURN_STALE_SECONDS` (module-private in the route) in milliseconds. */
const STALE_MS = 150_000;

/**
 * A turn that is *almost* stale, so the route's own timer is the only thing that
 * has to happen for it to tip over — the flip is observable in real time instead
 * of 150 s from now.
 */
const ALMOST_STALE_MS = STALE_MS - 400;

function msAgo(milliseconds: number): string {
  return new Date(Date.now() - milliseconds).toISOString();
}

function chat(
  id: string,
  attributes: Partial<components["schemas"]["ChatAttributes"]>,
): ChatResource {
  return {
    id,
    type: "chats",
    attributes: {
      title: null,
      activeOperationId: null,
      createdAt: minutesAgo(60),
      updatedAt: minutesAgo(60),
      ...attributes,
    },
  };
}

function message(
  id: string,
  role: components["schemas"]["ChatMessageRole"],
  body: string,
  createdAt: string,
): ChatMessageResource {
  return {
    id,
    type: "chat-messages",
    attributes: {
      role,
      body,
      toolCalls: [],
      sources: [],
      recommendations: [],
      createdAt,
    },
  };
}

/** The advisor's opener carries Markdown incl. a GFM table (the pinned config). */
const INTERVIEW_MESSAGES: readonly ChatMessageResource[] = [
  message(
    "01MESSAGEGREETING0000000001",
    "assistant",
    "Hello! **What licence do you hold**, and how much riding have you done?",
    "2026-08-25T09:02:00Z",
  ),
  message(
    "01MESSAGEUSER00000000000001",
    "user",
    "A2 since last month.\nI commute 20 km a day.",
    "2026-08-25T09:04:00Z",
  ),
  message(
    "01MESSAGEANSWER0000000000001",
    "assistant",
    `## What A2 means

| Class | Typical power |
| --- | --- |
| A2 naked twin | 35 kW |`,
    "2026-08-25T09:05:00Z",
  ),
];

/** How many times the chat detail was read — the 409 test's evidence. */
let chatReads = 0;

/**
 * A gate the POST waits behind, so the `sending` caption is observable at all: a
 * stubbed request otherwise resolves within the same tick as the keystroke.
 */
let postGate: Promise<void> | null = null;

function holdNextPost(): () => Promise<void> {
  let release = (): void => undefined;

  postGate = new Promise<void>((resolve) => {
    release = resolve;
  });

  return async () => {
    postGate = null;
    release();
    // One turn of the event loop, so the resolved request is delivered inside
    // the caller's `act` block rather than after it.
    await Promise.resolve();
  };
}

/**
 * The fake API: chat detail reads, the paginated timeline read, and a POST that
 * really appends the message and starts a turn (so "Seen" and the typing bubble
 * come from refetched server state, not from the mutation).
 */
function installApi() {
  const chats = new Map<string, ChatResource>([
    [CHAT_IDS.interview, chat(CHAT_IDS.interview, { title: "Commuter bike for the city" })],
    [
      CHAT_IDS.typing,
      chat(CHAT_IDS.typing, {
        title: "First big bike after the A2",
        activeOperationId: "01OPERATIONTYPING000000001",
      }),
    ],
    [
      CHAT_IDS.stale,
      chat(CHAT_IDS.stale, {
        title: "Weekend trips on a budget",
        activeOperationId: "01OPERATIONSTALE0000000001",
      }),
    ],
    [
      CHAT_IDS.new,
      chat(CHAT_IDS.new, {
        activeOperationId: "01OPERATIONGREETING0000001",
        createdAt: new Date().toISOString(),
      }),
    ],
    [
      CHAT_IDS.flip,
      chat(CHAT_IDS.flip, {
        title: "A turn about to be lost",
        activeOperationId: "01OPERATIONFLIP00000000001",
      }),
    ],
    [CHAT_IDS.empty, chat(CHAT_IDS.empty, {})],
  ]);

  const timelines = new Map<string, ChatMessageResource[]>([
    [CHAT_IDS.interview, [...INTERVIEW_MESSAGES]],
    [
      CHAT_IDS.typing,
      [
        message("01MESSAGETYPING00000000001", "assistant", "Welcome back!", minutesAgo(3)),
        // "Just now": the turn is young, so it is not stale.
        message("01MESSAGETYPING00000000002", "user", "Compare the CB500F with the Z650.", minutesAgo(0)),
      ],
    ],
    [
      CHAT_IDS.stale,
      [
        message("01MESSAGESTALE000000000001", "assistant", "Tell me what you ride today.", minutesAgo(20)),
        // Older than CHAT_TURN_STALE_SECONDS (150 s), so the turn is lost.
        message("01MESSAGESTALE000000000002", "user", "I'm on a 125.", minutesAgo(6)),
      ],
    ],
    [
      CHAT_IDS.flip,
      [
        message("01MESSAGEFLIP0000000000001", "assistant", "What do you ride now?", minutesAgo(9)),
        // Not stale yet — it becomes stale 400 ms from now, on the route's timer.
        message("01MESSAGEFLIP0000000000002", "user", "Nothing yet.", msAgo(ALMOST_STALE_MS)),
      ],
    ],
    [CHAT_IDS.new, []],
    [CHAT_IDS.empty, []],
  ]);

  let createdMessages = 0;

  chatReads = 0;

  function notFound(): Response {
    return jsonResponse(
      { errors: [{ status: "404", code: "not-found", detail: "gone" }] },
      { status: 404 },
    );
  }

  stubFetch(async (request) => {
    const url = new URL(request.url);

    if (url.pathname === "/api/chat-messages" && request.method === "GET") {
      const rows = timelines.get(url.searchParams.get("filter[chat]") ?? "");

      return rows === undefined
        ? notFound()
        : jsonResponse({ data: rows, meta: { totalCount: rows.length } });
    }

    if (url.pathname === "/api/chat-messages" && request.method === "POST") {
      const payload = (await request.json()) as components["schemas"]["ChatMessageCreateRequest"];
      const { chatId, body } = payload.data.attributes;
      const row = chats.get(chatId);
      const rows = timelines.get(chatId);

      if (row === undefined || rows === undefined) {
        return notFound();
      }

      if (postGate !== null) {
        await postGate;
      }

      if (body === FAILING_BODY) {
        return jsonResponse(
          { errors: [{ status: "500", code: "server-error", detail: "boom" }] },
          { status: 500 },
        );
      }

      if (body === CONFLICTING_BODY) {
        // A turn the client did not know about: the message is refused and
        // nothing is stored, but the chat now reports the pointer.
        chats.set(chatId, {
          ...row,
          attributes: { ...row.attributes, activeOperationId: "01OPERATIONRACE00000000001" },
        });

        return jsonResponse(
          { errors: [{ status: "409", code: "response-pending", detail: "busy" }] },
          { status: 409 },
        );
      }

      createdMessages += 1;

      // The server assigns its own ULID — it never echoes the client's localId.
      const created = message(
        `01MESSAGESERVER${String(createdMessages).padStart(11, "0")}`,
        "user",
        body,
        new Date().toISOString(),
      );

      rows.push(created);
      chats.set(chatId, {
        ...row,
        attributes: { ...row.attributes, activeOperationId: "01OPERATIONREPLY0000000001" },
      });

      return jsonResponse({ data: created }, { status: 201 });
    }

    if (url.pathname.startsWith("/api/chats/") && request.method === "GET") {
      chatReads += 1;

      const row = chats.get(url.pathname.split("/").at(-1) ?? "");

      return row === undefined ? notFound() : jsonResponse({ data: row });
    }

    throw new Error(`Unexpected ${request.method} ${request.url}`);
  });
}

/** The composer input; also the target of every keyboard interaction. */
function composer(): HTMLElement {
  return screen.getByRole("textbox", { name: "Message" });
}

function sendButton(): HTMLElement {
  return screen.getByRole("button", { name: "Send" });
}

beforeEach(() => {
  chatIdParam = CHAT_IDS.interview;
  postGate = null;
  installApi();
});

describe("ConsultationChatRoute — turn states", () => {
  it("row 5: an idle conversation shows its messages and nothing else", async () => {
    renderWithProviders(<ConsultationChatRoute />);

    const timeline = await screen.findByRole("log", { name: "Conversation" });

    // The advisor speaks first, and its Markdown renders (GFM table included).
    expect(within(timeline).getByRole("table")).toBeInTheDocument();
    // No turn is in flight: no typing bubble, no failed-turn row, no captions.
    expect(
      screen.queryByRole("status", { name: "The advisor is typing…" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Seen")).not.toBeInTheDocument();
    expect(screen.queryByText(/could not finish this reply/)).not.toBeInTheDocument();
  });

  it("row 3: an active turn shows the typing bubble and a Seen caption", async () => {
    chatIdParam = CHAT_IDS.typing;

    renderWithProviders(<ConsultationChatRoute />);

    expect(
      await screen.findByRole("status", { name: "The advisor is typing…" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Seen")).toBeInTheDocument();

    // The field stays editable — drafting while the advisor types is fine — but
    // sending waits for the turn to end.
    await userEvent.type(composer(), "One more thing");
    expect(composer()).toBeEnabled();
    expect(sendButton()).toBeDisabled();
  });

  it("row 3: the greeting turn shows the typing bubble without a Seen caption", async () => {
    chatIdParam = CHAT_IDS.new;

    renderWithProviders(<ConsultationChatRoute />);

    expect(
      await screen.findByRole("status", { name: "The advisor is typing…" }),
    ).toBeInTheDocument();
    // Nobody has said anything yet, so there is nothing to have been seen.
    expect(screen.queryByText("Seen")).not.toBeInTheDocument();
  });

  it("row 4: a stale turn replaces the typing bubble and re-enables sending", async () => {
    chatIdParam = CHAT_IDS.stale;

    renderWithProviders(<ConsultationChatRoute />);

    expect(
      await screen.findByText(/The advisor could not finish this reply/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("status", { name: "The advisor is typing…" }),
    ).not.toBeInTheDocument();

    await userEvent.type(composer(), "Trying again");
    expect(sendButton()).toBeEnabled();
  });

  it("row 4: a waiting turn goes stale on its own timer, even if the timer fires early", async () => {
    chatIdParam = CHAT_IDS.flip;

    // Chromium fires a long `setTimeout` a few milliseconds *early* — observed
    // 9 ms short of the real 150 s timer while verifying step 3.15. A frozen
    // clock models exactly that: the callback runs while `Date.now()` is still
    // behind the deadline. Recording `Date.now()` as the tick used to wedge this
    // state for good — the comparison failed and, `deadline` never changing, the
    // effect never re-armed, so the turn stayed "typing" as long as the page did.
    vi.spyOn(Date, "now").mockReturnValue(Date.now());

    renderWithProviders(<ConsultationChatRoute />);

    expect(
      await screen.findByRole("status", { name: "The advisor is typing…" }),
    ).toBeInTheDocument();

    // Nothing on the network moves; only the route's own timer does.
    expect(
      await screen.findByText(/The advisor could not finish this reply/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("status", { name: "The advisor is typing…" }),
    ).not.toBeInTheDocument();
  });

  it("an empty idle chat shows the intro hint instead of a timeline", async () => {
    chatIdParam = CHAT_IDS.empty;

    renderWithProviders(<ConsultationChatRoute />);

    expect(
      await screen.findByText("Tell the advisor about yourself"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("log")).not.toBeInTheDocument();
    expect(composer()).toBeEnabled();
  });

  it("answers an unknown chat with the not-found gate", async () => {
    chatIdParam = CHAT_IDS.gone;

    // A nested provider, only here: the application retries a failed query three
    // times with backoff (~7 s), and this test is about the gate, not the wait.
    // The page-level spinner is what the user sees until then.
    renderWithProviders(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ConsultationChatRoute />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(await screen.findByText("Consultation not found")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});

describe("ConsultationChatRoute — composer", () => {
  it("row 1: Enter sends, and the server row replaces the optimistic bubble", async () => {
    const user = userEvent.setup();

    renderWithProviders(<ConsultationChatRoute />);
    await screen.findByRole("log", { name: "Conversation" });

    const releasePost = holdNextPost();

    await user.type(composer(), "I ride 20 km a day.{Enter}");

    // The optimistic bubble is on screen before the request resolves, and the
    // composer is cleared immediately (the bubble now holds the text).
    expect(screen.getByText("Sending…")).toBeInTheDocument();
    expect(screen.getByText("I ride 20 km a day.")).toBeInTheDocument();
    expect(composer()).toHaveValue("");

    await act(releasePost);

    // A successful POST *is* the "seen" signal, and the advisor's turn begins —
    // the typing bubble comes from the refetched `activeOperationId`.
    await waitFor(() => {
      expect(screen.getByText("Seen")).toBeInTheDocument();
    });
    expect(
      screen.getByRole("status", { name: "The advisor is typing…" }),
    ).toBeInTheDocument();

    // The refetch delivered the server's own row: the optimistic entry is gone
    // rather than duplicated, even though the server echoes no `localId`.
    await waitFor(() => {
      expect(screen.getAllByText("I ride 20 km a day.")).toHaveLength(1);
    });
  });

  it("inserts a newline on Shift+Enter instead of sending", async () => {
    const user = userEvent.setup();

    chatIdParam = CHAT_IDS.empty;
    renderWithProviders(<ConsultationChatRoute />);
    await screen.findByText("Tell the advisor about yourself");

    await user.type(composer(), "First line{Shift>}{Enter}{/Shift}second line");

    expect(composer()).toHaveValue("First line\nsecond line");
    expect(screen.queryByText("Sending…")).not.toBeInTheDocument();
  });

  it("refuses an over-length message without sending it", async () => {
    chatIdParam = CHAT_IDS.empty;
    renderWithProviders(<ConsultationChatRoute />);
    await screen.findByText("Tell the advisor about yourself");

    // Pasted, not typed: 4001 keystrokes would take longer than the test.
    fireEvent.change(composer(), { target: { value: "x".repeat(4001) } });

    expect(screen.getByText("This message is too long.")).toBeInTheDocument();
    expect(sendButton()).toBeDisabled();
  });

  it("row 2: a failed send keeps the text and offers retry and discard", async () => {
    const user = userEvent.setup();

    chatIdParam = CHAT_IDS.empty;
    renderWithProviders(<ConsultationChatRoute />);
    await screen.findByText("Tell the advisor about yourself");

    await user.type(composer(), `${FAILING_BODY}{Enter}`);
    expect(await screen.findByText("Not sent.")).toBeInTheDocument();
    // The text lives in the bubble, and the empty composer cannot be sent.
    expect(sendButton()).toBeDisabled();
    expect(screen.getByText(FAILING_BODY)).toBeInTheDocument();

    // Retrying re-fires the same body in place rather than adding a second bubble.
    const releasePost = holdNextPost();

    await user.click(screen.getByRole("button", { name: "Send again" }));
    expect(screen.getByText("Sending…")).toBeInTheDocument();

    await act(releasePost);
    expect(await screen.findByText("Not sent.")).toBeInTheDocument();
    expect(screen.getAllByText(FAILING_BODY)).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Discard" }));
    expect(screen.queryByText("Not sent.")).not.toBeInTheDocument();
    expect(screen.queryByText(FAILING_BODY)).not.toBeInTheDocument();
  });

  it("treats a 409 response-pending as a quiet refetch of the chat", async () => {
    const user = userEvent.setup();

    renderWithProviders(<ConsultationChatRoute />);
    await screen.findByRole("log", { name: "Conversation" });

    const readsBefore = chatReads;

    await user.type(composer(), `${CONFLICTING_BODY}{Enter}`);

    // The message was refused, so the bubble keeps the text and its way out…
    expect(await screen.findByText("Not sent.")).toBeInTheDocument();
    // …and the chat detail is refetched instead of an error being shown, so the
    // UI learns about the turn it raced with.
    await waitFor(() => {
      expect(chatReads).toBeGreaterThan(readsBefore);
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
