import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { i18n } from "../i18n";
import { specComparisonCall } from "../test/chatFixtures";
import { renderWithProviders } from "../test/render";

import { SPEC_FIELD_KEYS } from "./specFields";
import { ToolResultSpecComparison } from "./ToolResultSpecComparison";
import { isSpecComparisonResult, type SpecComparisonResult } from "./toolResults";

/**
 * The comparison table: one column per bike, one row per frozen spec field, and
 * an em dash wherever nothing was verified.
 */

function fixtureResult(): SpecComparisonResult {
  const result = specComparisonCall.result;

  if (!isSpecComparisonResult(result)) {
    throw new Error("the pinned spec_comparison fixture no longer matches its schema");
  }

  return result;
}

describe("ToolResultSpecComparison", () => {
  it("labels every column and every frozen spec row", () => {
    renderWithProviders(<ToolResultSpecComparison result={fixtureResult()} />);

    const table = screen.getByRole("table", { name: "Spec comparison" });

    expect(within(table).getByRole("columnheader", { name: "Spec" })).toBeInTheDocument();
    for (const name of ["Honda CB500F", "Yamaha MT-07", "Kawasaki Z650"]) {
      expect(within(table).getByRole("columnheader", { name })).toBeInTheDocument();
    }

    // Label plus unit, and the frozen key drives the label.
    expect(within(table).getByRole("rowheader", { name: "Power (kW)" })).toBeInTheDocument();
    expect(within(table).getByRole("rowheader", { name: "Category" })).toBeInTheDocument();
    expect(within(table).getAllByRole("row")).toHaveLength(
      // One header row plus one row per frozen field.
      fixtureResult().rows.length + 1,
    );
  });

  it("renders an unverified value as an em dash carrying its meaning", () => {
    renderWithProviders(<ToolResultSpecComparison result={fixtureResult()} />);

    const unknownCells = screen.getAllByLabelText("Unknown");

    // torqueNm, seatHeightMm, topSpeedKmh ×2, msrpEur — every explicit null.
    expect(unknownCells).toHaveLength(5);
    for (const cell of unknownCells) {
      expect(cell).toHaveTextContent("—");
    }
  });

  it("translates flags and keeps backend enum values verbatim", () => {
    renderWithProviders(<ToolResultSpecComparison result={fixtureResult()} />);

    const absRow = screen.getByRole("rowheader", { name: "ABS" }).closest("tr");

    expect(absRow).not.toBeNull();
    expect(within(absRow as HTMLElement).getAllByRole("cell").map((c) => c.textContent))
      .toEqual(["Yes", "Yes", "No"]);

    const categoryRow = screen.getByRole("rowheader", { name: "Category" }).closest("tr");

    expect(
      within(categoryRow as HTMLElement).getAllByRole("cell").map((c) => c.textContent),
    ).toEqual(["naked", "naked", "naked"]);
  });

  it("renders a spec field this build predates verbatim", () => {
    renderWithProviders(
      <ToolResultSpecComparison
        result={{
          bikes: [{ motorbikeId: "01BIKE", name: "Honda CB500F" }],
          rows: [{ field: "wheelbaseMm", values: [1410] }],
        }}
      />,
    );

    expect(screen.getByRole("rowheader", { name: "wheelbaseMm" })).toBeInTheDocument();
  });

  it("scrolls horizontally instead of dropping a column", () => {
    const { container } = renderWithProviders(
      <ToolResultSpecComparison result={fixtureResult()} />,
    );
    const scroller = container.querySelector(".MuiTableContainer-root");

    expect(scroller).not.toBeNull();
    expect(scroller).toHaveStyle({ overflowX: "auto" });
  });

  it("has a label for every frozen spec field", () => {
    for (const field of SPEC_FIELD_KEYS) {
      const key = `consultations.specFields.${field}` as const;

      // A missing key would reach the table head as raw "consultations.…" text.
      expect(i18n.t(key)).not.toBe(key);
    }
  });
});
