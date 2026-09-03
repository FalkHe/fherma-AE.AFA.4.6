import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../test/render";

import { UntrustedMarkdown } from "./UntrustedMarkdown";

/**
 * The shared markdown config, proven once: raw HTML off, GFM tables, links
 * through the base `ExternalLink`, and a `components` override merged over
 * (not replacing) that base — the per-site tests prove the wiring, this file
 * proves the config.
 */

describe("UntrustedMarkdown", () => {
  it("renders raw HTML as literal text, never as elements", () => {
    const body = `<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>`;

    const { container } = renderWithProviders(<UntrustedMarkdown>{body}</UntrustedMarkdown>);

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script>");
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });

  it("renders a markdown link opening in a new tab", () => {
    renderWithProviders(<UntrustedMarkdown>{"[docs](https://example.org)"}</UntrustedMarkdown>);

    const link = screen.getByRole("link", { name: "docs" });

    expect(link).toHaveAttribute("href", "https://example.org");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders a GFM table", () => {
    const body = "| A | B |\n| --- | --- |\n| 1 | 2 |\n";

    renderWithProviders(<UntrustedMarkdown>{body}</UntrustedMarkdown>);

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "A" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "2" })).toBeInTheDocument();
  });

  it("applies a components override while still routing links through ExternalLink", () => {
    const body = "| A |\n| --- |\n| 1 |\n\n[docs](https://example.org)";

    renderWithProviders(
      <UntrustedMarkdown
        components={{ table: ({ children }) => <table data-custom="yes">{children}</table> }}
      >
        {body}
      </UntrustedMarkdown>,
    );

    expect(screen.getByRole("table")).toHaveAttribute("data-custom", "yes");

    const link = screen.getByRole("link", { name: "docs" });

    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
});
