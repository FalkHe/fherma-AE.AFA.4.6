import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import type { components } from "../api/schema";
import { jsonResponse, stubFetch } from "../test/network";
import { renderWithProviders } from "../test/render";

import { ConsultationsRoute } from "./ConsultationsRoute";

/**
 * The consultation list against a small in-memory `chats` API behind the `fetch`
 * stub: what a row shows, that "Ask the advisor" sends the strict empty envelope
 * and navigates to the created consultation, and the delete affordance end to end
 * (row → confirmation → row gone).
 */

type ChatResource = components["schemas"]["ChatResource"];

const IDS = {
  interview: "01CHATINTERVIEW00000000001",
  replying: "01CHATREPLYING0000000000001",
  untitled: "01CHATUNTITLED0000000000001",
  created: "01CHATCREATED00000000000001",
} as const;

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
      createdAt: "2026-08-25T09:00:00Z",
      updatedAt: "2026-08-25T09:00:00Z",
      ...attributes,
    },
  };
}

/** Three consultations, most recent activity first — the server's pinned order. */
const FIXTURE_CHATS: readonly ChatResource[] = [
  chat(IDS.replying, {
    title: "First big bike after the A2",
    activeOperationId: "01OPERATIONREPLYING00000001",
    updatedAt: "2026-08-27T08:30:00Z",
  }),
  chat(IDS.interview, {
    title: "Commuter bike for the city",
    updatedAt: "2026-08-26T14:02:00Z",
  }),
  chat(IDS.untitled, { updatedAt: "2026-08-20T09:15:00Z" }),
];

/** Recorded outgoing writes, so the request shape can be asserted. */
let posted: unknown[] = [];

/** The fake API: the list read, the create, and a DELETE that really removes a row. */
function installApi() {
  let chats = [...FIXTURE_CHATS];

  posted = [];

  stubFetch(async (request) => {
    const url = new URL(request.url);

    if (url.pathname === "/api/chats" && request.method === "GET") {
      return jsonResponse({ data: chats, meta: { totalCount: chats.length } });
    }

    if (url.pathname === "/api/chats" && request.method === "POST") {
      posted.push(await request.json());

      const created = chat(IDS.created, {
        activeOperationId: "01OPERATIONGREETING00000001",
      });

      chats = [created, ...chats];

      return jsonResponse({ data: created }, { status: 201 });
    }

    if (url.pathname.startsWith("/api/chats/") && request.method === "DELETE") {
      const id = url.pathname.split("/").at(-1);

      chats = chats.filter((row) => row.id !== id);

      return new Response(null, { status: 204 });
    }

    throw new Error(`Unexpected ${request.method} ${request.url}`);
  });
}

function LocationProbe() {
  const { pathname } = useLocation();

  return <output data-testid="pathname">{pathname}</output>;
}

function renderRoute() {
  return renderWithProviders(
    <>
      <ConsultationsRoute />
      <LocationProbe />
    </>,
  );
}

beforeEach(() => {
  installApi();
});

describe("ConsultationsRoute", () => {
  it("lists the consultations with their last activity and the replying hint", async () => {
    renderRoute();

    const list = await screen.findByRole("list", { name: "Your consultations" });
    const rows = within(list).getAllByRole("listitem");

    // Three consultations, in the server's order (last activity first).
    expect(rows).toHaveLength(3);
    expect(
      within(list).getByRole("link", { name: /Commuter bike for the city/ }),
    ).toHaveAttribute("href", `/consultations/${IDS.interview}`);
    // A chat with a turn in flight says so in words, not only in colour.
    expect(within(list).getAllByText("Advisor is replying…")).toHaveLength(1);
    // A chat the server has not titled yet falls back to a label.
    expect(within(list).getAllByText("New consultation")).toHaveLength(1);
    // Every row can be deleted.
    expect(
      within(list).getAllByRole("button", { name: "Delete consultation" }),
    ).toHaveLength(3);
  });

  it("starts a consultation with the empty envelope and opens it", async () => {
    const user = userEvent.setup();

    renderRoute();
    await screen.findByRole("list", { name: "Your consultations" });

    await user.click(screen.getByRole("button", { name: "Ask the advisor" }));

    // The endpoint takes no attributes at all — the payload exists to be
    // validated, so an invented one would be a 422.
    await waitFor(() => {
      expect(posted).toEqual([{ data: { type: "chats", attributes: {} } }]);
    });
    // The advisor opens the conversation, so the created chat is navigated to.
    await waitFor(() => {
      expect(screen.getByTestId("pathname")).toHaveTextContent(
        `/consultations/${IDS.created}`,
      );
    });
  });

  it("deletes a consultation after the confirmation dialog", async () => {
    const user = userEvent.setup();

    renderRoute();

    const list = await screen.findByRole("list", { name: "Your consultations" });
    const row = within(list)
      .getByRole("link", { name: /Commuter bike for the city/ })
      .closest("li");

    if (row === null) {
      throw new Error("The consultation row is not a list item.");
    }

    await user.click(
      within(row).getByRole("button", { name: "Delete consultation" }),
    );

    const dialog = await screen.findByRole("dialog");

    // The title is interpolated, so it is clear which conversation goes away.
    expect(
      within(dialog).getByText(/“Commuter bike for the city” and its conversation/),
    ).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    // The dialog closes on success first — while it is open MUI hides the rest
    // of the page from the accessibility tree, so the row cannot be asserted on
    // until then.
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(
        screen.queryByRole("link", { name: /Commuter bike for the city/ }),
      ).not.toBeInTheDocument();
    });
    expect(within(screen.getByRole("list")).getAllByRole("listitem")).toHaveLength(2);
  });
});
