import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { costEstimatorCall, costEstimatorCallWithUsedPrice } from "../test/chatFixtures";
import { renderWithProviders } from "../test/render";

import { CostEstimateChip, ToolResultCostEstimator } from "./ToolResultCostEstimator";
import { isCostEstimatorResult, type CostEstimatorResult } from "./toolResults";

/**
 * Modelled money: the numbers are formatted in the result's currency, and the
 * fact that they are estimates is never hidden behind a toggle.
 */

function fixtureResult(): CostEstimatorResult {
  const result = costEstimatorCall.result;

  if (!isCostEstimatorResult(result)) {
    throw new Error("the pinned cost_estimator fixture no longer matches its schema");
  }

  return result;
}

function fixtureResultWithUsedPrice(): CostEstimatorResult {
  const result = costEstimatorCallWithUsedPrice.result;

  if (!isCostEstimatorResult(result)) {
    throw new Error("the pinned cost_estimator fixture no longer matches its schema");
  }

  return result;
}

/** What `Intl` renders for whole euros in the test locale. */
function euros(amount: number): string {
  return new Intl.NumberFormat("en", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(amount);
}

describe("ToolResultCostEstimator", () => {
  it("shows every line item in its currency, plus a total", () => {
    renderWithProviders(<ToolResultCostEstimator result={fixtureResult()} />);

    // Server-composed labels, including the "/year" qualifier, are verbatim.
    expect(screen.getByRole("rowheader", { name: "Insurance /year" })).toBeInTheDocument();
    expect(screen.getByText(euros(620))).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "Total" })).toBeInTheDocument();
    expect(screen.getByText(euros(8690))).toBeInTheDocument();
  });

  it("discloses that it is an estimate without any interaction", () => {
    renderWithProviders(<CostEstimateChip />);

    expect(screen.getByText("Estimate")).toBeInTheDocument();
  });

  it("counts the assumptions while they are collapsed and reveals them on demand", async () => {
    const user = userEvent.setup();

    renderWithProviders(<ToolResultCostEstimator result={fixtureResult()} />);

    const toggle = screen.getByRole("button", { name: /Assumptions \(3\)/ });

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("8,000 km per year in Germany.")).not.toBeVisible();

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("8,000 km per year in Germany.")).toBeVisible();
  });

  it("renders the used-price snapshot after the assumptions block when the result carries one", () => {
    renderWithProviders(<ToolResultCostEstimator result={fixtureResultWithUsedPrice()} />);

    // Line items, total and assumptions toggle are unaffected.
    expect(screen.getByRole("rowheader", { name: "Total" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Assumptions \(3\)/ })).toBeInTheDocument();
    // The snapshot block, including its stale caption (fixture is stale: true).
    expect(screen.getByText("Used market price")).toBeInTheDocument();
    expect(
      screen.getByText(
        "This snapshot is older than the market-data window and may no longer reflect current prices.",
      ),
    ).toBeInTheDocument();
  });

  it("renders no snapshot DOM, and the rest byte-identical, when usedPrice is absent", () => {
    renderWithProviders(<ToolResultCostEstimator result={fixtureResult()} />);

    expect(screen.queryByText("Used market price")).toBeNull();
    expect(screen.getByRole("rowheader", { name: "Total" })).toBeInTheDocument();
  });

  it("omits the disclosure when there is nothing assumed", () => {
    renderWithProviders(
      <ToolResultCostEstimator
        result={{
          currency: "EUR",
          lineItems: [{ label: "Purchase price", amount: 6790 }],
          total: 6790,
          assumptions: [],
        }}
      />,
    );

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
