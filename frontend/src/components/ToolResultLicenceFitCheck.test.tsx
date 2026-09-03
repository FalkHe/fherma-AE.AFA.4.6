import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { licenceFitCheckCall } from "../test/chatFixtures";
import { renderWithProviders } from "../test/render";

import { ToolResultLicenceFitCheck } from "./ToolResultLicenceFitCheck";
import { isLicenceFitCheckResult, type LicenceFitCheckResult } from "./toolResults";

/**
 * Verdict plus the arithmetic behind it — an unexplained verdict is an opinion.
 */

function fixtureResult(): LicenceFitCheckResult {
  const result = licenceFitCheckCall.result;

  if (!isLicenceFitCheckResult(result)) {
    throw new Error("the pinned licence_fit_check fixture no longer matches its schema");
  }

  return result;
}

describe("ToolResultLicenceFitCheck", () => {
  it("labels each verdict in words, not only in colour", () => {
    renderWithProviders(<ToolResultLicenceFitCheck result={fixtureResult()} />);

    expect(screen.getByText("Pass")).toBeInTheDocument();
    expect(screen.getByText("Fail")).toBeInTheDocument();
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });

  it("shows the server's rule labels and evidence verbatim", () => {
    renderWithProviders(<ToolResultLicenceFitCheck result={fixtureResult()} />);

    expect(screen.getByText("A2 power limit")).toBeInTheDocument();
    expect(screen.getByText("35.0 kW ≤ 35 kW")).toBeInTheDocument();
    expect(
      screen.getByText("54.0 kW / 184 kg = 0.293 kW/kg > 0.20 kW/kg"),
    ).toBeInTheDocument();
    // An `unknown` verdict carries its reason in the same place.
    expect(
      screen.getByText("Seat height not verified for this model."),
    ).toBeInTheDocument();
  });

  it("renders a rule without evidence without an empty caption", () => {
    renderWithProviders(
      <ToolResultLicenceFitCheck
        result={{
          rules: [
            { rule: "a2_power", label: "A2 power limit", verdict: "pass", evidence: null },
          ],
        }}
      />,
    );

    expect(screen.getByText("A2 power limit")).toBeInTheDocument();
    expect(screen.getByText("Pass")).toBeInTheDocument();
  });
});
