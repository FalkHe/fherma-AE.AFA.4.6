import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "../hooks/useChatMessages";
import { kitchenSinkMessage } from "../test/chatFixtures";
import { renderWithProviders } from "../test/render";

import { MessageBubble } from "./MessageBubble";

/**
 * The two stylings of one component, and the rule that separates them: the
 * advisor's body is Markdown, the user's never is — plus the pinned order of
 * the advisor's parts (ui-spec §6), proven on the kitchen-sink message.
 */

const EMPTY_PARTS = { toolCalls: [], sources: [], recommendations: [] };

/** Today at 09:15 local time — always the same calendar day as "now". */
function todayAt(): string {
  const timestamp = new Date();

  timestamp.setHours(9, 15, 0, 0);

  return timestamp.toISOString();
}

function message(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "01STUBMSG00000000000000001",
    role: "assistant",
    body: "Hello.",
    ...EMPTY_PARTS,
    createdAt: todayAt(),
    ...overrides,
  };
}

const MARKDOWN_BODY = `## Shortlist

- A2 legal
- low seat

| Class | Power |
| --- | --- |
| A2 naked twin | 35 kW |
`;

describe("MessageBubble", () => {
  it("renders an advisor message as Markdown, including GFM tables", () => {
    renderWithProviders(<MessageBubble message={message({ body: MARKDOWN_BODY })} />);

    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Shortlist");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);

    const table = screen.getByRole("table");

    expect(within(table).getByRole("columnheader", { name: "Class" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "35 kW" })).toBeInTheDocument();
  });

  it("renders raw HTML in an advisor message as inert text, links as ExternalLink", () => {
    const HTML_BODY =
      "<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n[docs](https://example.org)";

    const { container } = renderWithProviders(
      <MessageBubble message={message({ body: HTML_BODY })} />,
    );

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script>");
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");

    const link = screen.getByRole("link", { name: "docs" });

    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders a user message as plain pre-wrapped text, never as Markdown", () => {
    renderWithProviders(
      <MessageBubble message={message({ role: "user", body: MARKDOWN_BODY })} />,
    );

    // The Markdown source is on screen verbatim: no heading, no table.
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText(/## Shortlist/)).toHaveStyle({ whiteSpace: "pre-wrap" });
  });

  it("shows the time for a message from today and the date for an older one", () => {
    const sameDay = todayAt();
    const olderDay = "2026-08-20T09:15:00Z";

    renderWithProviders(
      <>
        <MessageBubble message={message({ createdAt: sameDay })} />
        <MessageBubble message={message({ id: "other", createdAt: olderDay })} />
      </>,
    );

    expect(
      screen.getByText(new Date(sameDay).toLocaleTimeString("en", { timeStyle: "short" })),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        new Date(olderDay).toLocaleString("en", {
          dateStyle: "medium",
          timeStyle: "short",
        }),
      ),
    ).toBeInTheDocument();
  });

  it("replaces the timestamp with the send state while a message is in flight", () => {
    const { unmount } = renderWithProviders(
      <MessageBubble message={message({ role: "user" })} state="sending" />,
    );

    expect(screen.getByText("Sending…")).toBeInTheDocument();
    unmount();

    renderWithProviders(<MessageBubble message={message({ role: "user" })} state="sent" />);

    expect(screen.getByText("Seen")).toBeInTheDocument();
  });

  it("offers retry and discard on a failed send", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const onDiscard = vi.fn();

    renderWithProviders(
      <MessageBubble
        message={message({ role: "user", body: "Not delivered" })}
        state="failed"
        onRetry={onRetry}
        onDiscard={onDiscard}
      />,
    );

    // Colour is never the only signal for the failure.
    expect(screen.getByText("Not sent.")).toBeInTheDocument();
    // The bubble still holds the text, so retry has something to re-send.
    expect(screen.getByText("Not delivered")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Send again" }));
    await user.click(screen.getByRole("button", { name: "Discard" }));

    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onDiscard).toHaveBeenCalledTimes(1);
  });

  it("renders every part of the kitchen-sink message", () => {
    renderWithProviders(<MessageBubble message={kitchenSinkMessage} />);

    // All four styled tool blocks, labelled.
    for (const label of [
      "Catalogue search",
      "Spec comparison",
      "Licence & fit check",
      "Cost estimate",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // The generic fallback for the tool this build predates.
    expect(screen.getByText("some_future_tool")).toBeInTheDocument();
    // Both subtle rows.
    expect(
      screen.getByText("Preference noted — budget: up to €7,000 (must-have)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("“Bimota Tesi H2” isn't in our catalogue yet — noted for research."),
    ).toBeInTheDocument();
    // The answer itself.
    expect(screen.getByText(/here is the shortlist/)).toBeInTheDocument();
    // Two cards, one of them without an image.
    expect(screen.getByText("Recommended for you")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(2);
    expect(screen.getAllByRole("img")).toHaveLength(1);
    // Three chunks, two of them citing the same page.
    expect(screen.getByRole("button", { name: /Sources \(2\)/ })).toBeInTheDocument();
  });

  it("keeps the advisor's parts in the pinned order", () => {
    renderWithProviders(<MessageBubble message={kitchenSinkMessage} />);

    const order = [
      screen.getByText("Catalogue search"),
      screen.getByText(/here is the shortlist/),
      screen.getByText("Recommended for you"),
      screen.getByRole("button", { name: /Sources \(2\)/ }),
    ];

    // What the advisor did → the answer → the payoff → the receipts.
    for (const [index, node] of order.slice(0, -1).entries()) {
      expect(
        node.compareDocumentPosition(order[index + 1]) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
  });
});
