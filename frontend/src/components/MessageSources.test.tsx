import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { kitchenSinkSources } from "../test/chatFixtures";
import { renderWithProviders } from "../test/render";

import { MessageSources } from "./MessageSources";

/**
 * The receipts: discoverable at a glance (a count), out of the way by default,
 * and every link leaves the application.
 */

describe("MessageSources", () => {
  it("counts the distinct sources and keeps the list collapsed", () => {
    renderWithProviders(<MessageSources sources={kitchenSinkSources} />);

    // Three chunks, two of which cite the same page: two distinct sources.
    const toggle = screen.getByRole("button", { name: /Sources \(2\)/ });

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    // Collapsed means hidden from the accessibility tree, not merely off-screen.
    expect(screen.queryByRole("list", { name: "Sources" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Sources")).not.toBeVisible();
  });

  it("reveals the sources with their host and heading path", async () => {
    const user = userEvent.setup();

    renderWithProviders(<MessageSources sources={kitchenSinkSources} />);

    await user.click(screen.getByRole("button", { name: /Sources \(2\)/ }));

    const list = screen.getByRole("list", { name: "Sources" });

    expect(list).toBeVisible();
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(
      within(list).getByText("en.wikipedia.org · Honda CB500F › Reception"),
    ).toBeInTheDocument();
    expect(within(list).getByText("www.motorcyclenews.com")).toBeInTheDocument();
  });

  it("links every source out of the application", async () => {
    const user = userEvent.setup();

    renderWithProviders(<MessageSources sources={kitchenSinkSources} />);

    await user.click(screen.getByRole("button", { name: /Sources \(2\)/ }));

    const link = screen.getByRole("link", { name: /Honda CB500F/ });

    expect(link).toHaveAttribute("href", "https://en.wikipedia.org/wiki/Honda_CB500F");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("shows a source without a URL as plain text", async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <MessageSources
        sources={[
          {
            ...kitchenSinkSources[0],
            sourceUrl: null,
            sourceTitle: "Uploaded brochure",
            headingPath: null,
          },
        ]}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Sources \(1\)/ }));

    expect(screen.getByText("Uploaded brochure")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders nothing when the answer needed no retrieval", () => {
    const { container } = renderWithProviders(<MessageSources sources={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
