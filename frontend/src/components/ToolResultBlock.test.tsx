import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ToolCall } from "../hooks/useChatMessages";
import {
  catalogueSearchCall,
  costEstimatorCall,
  flagUnknownBikeCall,
  licenceFitCheckCall,
  recordPreferenceCall,
  specComparisonCall,
  unknownToolCall,
} from "../test/chatFixtures";
import { renderWithProviders } from "../test/render";

import { ToolResultBlock } from "./ToolResultBlock";

/**
 * The frame and the dispatch: every executed call is visible without
 * interaction, and no result shape can make a call disappear.
 */

describe("ToolResultBlock", () => {
  it("labels each known tool and renders its styled body", () => {
    renderWithProviders(
      <>
        <ToolResultBlock toolCall={catalogueSearchCall} />
        <ToolResultBlock toolCall={specComparisonCall} />
        <ToolResultBlock toolCall={licenceFitCheckCall} />
        <ToolResultBlock toolCall={costEstimatorCall} />
      </>,
    );

    expect(screen.getByText("Catalogue search")).toBeInTheDocument();
    expect(screen.getByText("Spec comparison")).toBeInTheDocument();
    expect(screen.getByText("Licence & fit check")).toBeInTheDocument();
    expect(screen.getByText("Cost estimate")).toBeInTheDocument();

    // The bodies, one probe each.
    expect(screen.getByText("naked · 35 kW · 189 kg")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Spec comparison" })).toBeInTheDocument();
    expect(screen.getByText("35.0 kW ≤ 35 kW")).toBeInTheDocument();
    // The estimate disclosure sits in the header frame, always visible.
    expect(screen.getByText("Estimate")).toBeInTheDocument();
  });

  it("renders the bookkeeping tools as one-line caption rows", () => {
    renderWithProviders(
      <>
        <ToolResultBlock toolCall={recordPreferenceCall} />
        <ToolResultBlock toolCall={flagUnknownBikeCall} />
      </>,
    );

    expect(
      screen.getByText("Preference noted — budget: up to €7,000 (must-have)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("“Bimota Tesi H2” isn't in our catalogue yet — noted for research."),
    ).toBeInTheDocument();
    // Subtle rows carry no frame and no table.
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("falls back to the generic renderer for a tool it has never seen", () => {
    renderWithProviders(<ToolResultBlock toolCall={unknownToolCall} />);

    // The raw tool name is the label — deliberately untranslated.
    expect(screen.getByText("some_future_tool")).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "headline" })).toBeInTheDocument();
    expect(screen.getByText('"Ride-out planner"')).toBeInTheDocument();
    // A nested value is pretty-printed rather than stringified into one line.
    expect(screen.getByText(/"Stelvio"/)).toBeInTheDocument();
  });

  it("falls back to the generic renderer when a known tool answers another shape", () => {
    // The shared name-resolution failure: no `results`, so no styled list.
    const unresolvable: ToolCall = {
      ...catalogueSearchCall,
      result: { unknownBike: "Bimota Tesi H2" },
    };

    renderWithProviders(<ToolResultBlock toolCall={unresolvable} />);

    expect(screen.queryByText("Catalogue search")).not.toBeInTheDocument();
    expect(screen.getByText("catalogue_search")).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "unknownBike" })).toBeInTheDocument();
    expect(screen.getByText('"Bimota Tesi H2"')).toBeInTheDocument();
  });

  it("keeps a failed call visible, and says what went wrong", () => {
    const failed: ToolCall = {
      id: "01TOOLCALLFAILED",
      tool: "cost_estimator",
      arguments: { name: "Honda CB500F" },
      result: {},
      status: "failed",
      error: "Cost coefficients unavailable.",
    };

    renderWithProviders(<ToolResultBlock toolCall={failed} />);

    expect(screen.getByText("cost_estimator")).toBeInTheDocument();
    expect(screen.queryByText("Cost estimate")).not.toBeInTheDocument();
    // A failed call carries `result: {}`, so without the note the block would be
    // a label over nothing and the reader could not tell "found nothing" from
    // "broke". The message is server-composed and rendered verbatim.
    expect(screen.getByText("Cost coefficients unavailable.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows no error note on a succeeded call", () => {
    renderWithProviders(<ToolResultBlock toolCall={unknownToolCall} />);

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.queryByText(/unavailable/)).not.toBeInTheDocument();
  });
});
