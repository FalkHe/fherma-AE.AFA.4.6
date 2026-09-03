import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CatalogueModelDetail, CatalogueVariant } from "../hooks/useCatalogueModel";
import { i18n } from "../i18n";
import { renderWithProviders } from "../test/render";

import { ModelSpecTable } from "./ModelSpecTable";
import { SPEC_FIELD_KEYS, specFieldLabel } from "./specFields";

/**
 * The two things the detail fixtures cannot show: that the four groups together
 * cover **every** frozen spec field (a field added to the contract must not
 * silently disappear from the customer's page), and a model approved without any
 * verified specification at all.
 */

const EMPTY_SPECS: CatalogueModelDetail["specs"] = {
  category: null,
  engineCc: null,
  cylinders: null,
  powerKw: null,
  torqueNm: null,
  wetWeightKg: null,
  seatHeightMm: null,
  tankCapacityL: null,
  topSpeedKmh: null,
  abs: null,
  a2Eligible: null,
  priceBand: null,
  msrpEur: null,
};

const FULL_SPECS: CatalogueModelDetail["specs"] = {
  category: "naked",
  engineCc: 599,
  cylinders: 4,
  powerKw: 72.5,
  torqueNm: 63.5,
  wetWeightKg: 197,
  seatHeightMm: 785,
  tankCapacityL: 16.5,
  topSpeedKmh: 230,
  abs: true,
  a2Eligible: false,
  priceBand: "budget",
  msrpEur: 4200,
};

const TWO_VARIANTS: CatalogueVariant[] = [
  {
    slug: "comfort",
    name: "Comfort",
    description: "Adds anti-lock braking as standard.",
    specs: null,
  },
  {
    slug: "sport",
    name: "Sport",
    description: "Adjustable suspension and a sportier seat.",
    specs: { wetWeightKg: 192, seatHeightMm: 800 },
  },
];

describe("ModelSpecTable", () => {
  it("renders every frozen spec field exactly once, in four groups", () => {
    renderWithProviders(<ModelSpecTable specs={FULL_SPECS} />);

    const table = screen.getByRole("table", { name: "Verified specifications" });
    const labels = within(table)
      .getAllByRole("rowheader")
      .map((cell) => cell.textContent);

    expect([...labels].sort()).toEqual(
      SPEC_FIELD_KEYS.map((field) => specFieldLabel(i18n.t, field)).sort(),
    );
    for (const group of [
      "Engine & performance",
      "Dimensions & ergonomics",
      "Licence & safety",
      "Classification & price",
    ]) {
      expect(within(table).getByText(group)).toBeInTheDocument();
    }
  });

  it("replaces the table with one sentence when nothing is verified", () => {
    renderWithProviders(<ModelSpecTable specs={EMPTY_SPECS} />);

    expect(screen.getByText("Verified specifications")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
    expect(
      screen.getByText("No verified specifications are available for this model yet."),
    ).toBeInTheDocument();
  });

  it("appends one Trims row per trim that carries a spec delta (ui-spec §3.2)", () => {
    renderWithProviders(<ModelSpecTable specs={FULL_SPECS} variants={TWO_VARIANTS} />);

    const table = screen.getByRole("table", { name: "Verified specifications" });

    expect(within(table).getByText("Trims")).toBeInTheDocument();
    expect(within(table).getByRole("rowheader", { name: "Sport" })).toBeInTheDocument();
    expect(
      within(table).getByText("Wet weight: 192 kg · Seat height: 800 mm"),
    ).toBeInTheDocument();
    // Description-only trims never earn a row of their own.
    expect(within(table).queryByText("Comfort")).toBeNull();
  });

  it("renders no Trims group when `variants` is absent or empty", () => {
    const { rerender } = renderWithProviders(<ModelSpecTable specs={FULL_SPECS} />);

    expect(screen.queryByText("Trims")).toBeNull();

    rerender(<ModelSpecTable specs={FULL_SPECS} variants={[]} />);
    expect(screen.queryByText("Trims")).toBeNull();
  });
});
