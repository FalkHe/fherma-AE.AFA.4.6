import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { CatalogueModelDetail } from "../hooks/useCatalogueModel";
import type { Manufacturer } from "../hooks/useCatalogueModels";
import type { ProductSuggestion } from "../hooks/useProductReview";
import { i18n } from "../i18n";
import { renderWithProviders } from "../test/render";

import {
  collapseClaimedYears,
  formatClaimedTypeCodes,
  formatClaimedYears,
  matchManufacturerClaim,
  unionTypeCodes,
} from "./claimLogic";
import { ClaimFieldRow, ModelClaimPanel } from "./ModelClaimPanel";

/**
 * The unverified-claim block (ui-spec §2) and its D6 boundary.
 *
 * "suggestion present → panel + per-field rows", "use claim on years",
 * "manufacturer claim with no matching option" and "suggestion null → no
 * panel" (§2.4 Test hooks) are exercised through `ModelIdentityPanel`, which
 * is the only component that ever passes claim data to `ModelClaimPanel` —
 * so this file tests `ModelClaimPanel` and its pure helpers directly, plus
 * the two D6 boundary proofs the step asks for explicitly.
 */

const SUGGESTION: ProductSuggestion = {
  source: "bike-list.txt",
  raw: "BMW R 1250 GS (K50) 2019–2023 ([Wikipedia][3])",
  manufacturer: "BMW",
  model: "R 1250 GS",
  yearFrom: 2019,
  yearTo: 2023,
  inProduction: false,
  yearRanges: [{ from: 2019, to: 2023 }],
  typeCodes: ["K50"],
  links: ["https://en.wikipedia.org/wiki/BMW_R1250GS"],
};

const MANUFACTURERS: Manufacturer[] = [
  { id: "01MANUFACTURERBMW00000001", name: "BMW" },
  { id: "01MANUFACTURERHONDA0000001", name: "Honda" },
];

describe("ModelClaimPanel", () => {
  it("renders the claim box: chip, hint, listed-as, source and links", () => {
    renderWithProviders(<ModelClaimPanel suggestion={SUGGESTION} />);

    expect(screen.getByText("Unverified claim")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Imported from a suggestion list — research must confirm it before it becomes catalogue data.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText((_, element) => element?.textContent === `"${SUGGESTION.raw}"`),
    ).toBeInTheDocument();
    expect(screen.getByText("bike-list.txt")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "https://en.wikipedia.org/wiki/BMW_R1250GS" }),
    ).toHaveAttribute("target", "_blank");
  });

  it("renders collapsed inside an Accordion for an approved row, hiding the hint until expanded", () => {
    renderWithProviders(<ModelClaimPanel suggestion={SUGGESTION} collapsed />);

    expect(screen.getByText("Unverified claim")).toBeInTheDocument();
    // The hint line is part of the always-expanded layout only.
    expect(
      screen.queryByText(
        "Imported from a suggestion list — research must confirm it before it becomes catalogue data.",
      ),
    ).not.toBeInTheDocument();
  });
});

describe("ClaimFieldRow", () => {
  it("renders a working Use-claim button when onUse is provided", async () => {
    let used = false;

    renderWithProviders(
      <ClaimFieldRow
        value="2019–2023"
        useLabel="Use claim"
        useA11yLabel="Use the claimed year"
        onUse={() => {
          used = true;
        }}
      />,
    );

    expect(screen.getByText("Claim: 2019–2023")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Use the claimed year" }));

    expect(used).toBe(true);
  });

  it("shows the no-match caption instead of a button when onUse is absent", () => {
    renderWithProviders(
      <ClaimFieldRow
        value="BMW"
        useLabel="Use claim"
        useA11yLabel="Use the claimed manufacturer"
        noMatchCaption="No matching manufacturer in the catalogue."
      />,
    );

    expect(
      screen.getByText("No matching manufacturer in the catalogue."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Use claim" })).not.toBeInTheDocument();
  });
});

describe("claim matching/collapse helpers (§2.3)", () => {
  it("matches a manufacturer claim case-insensitively against the loaded options", () => {
    expect(matchManufacturerClaim({ ...SUGGESTION, manufacturer: "bmw" }, MANUFACTURERS)).toEqual(
      MANUFACTURERS[0],
    );
    expect(
      matchManufacturerClaim({ ...SUGGESTION, manufacturer: "Kawasaki" }, MANUFACTURERS),
    ).toBeNull();
    expect(
      matchManufacturerClaim({ ...SUGGESTION, manufacturer: null }, MANUFACTURERS),
    ).toBeNull();
  });

  it("collapses a single claimed range into yearFrom/yearTo", () => {
    expect(collapseClaimedYears(SUGGESTION)).toEqual({ yearFrom: 2019, yearTo: 2023 });
  });

  it("collapses an in-production claim to a null yearTo", () => {
    expect(
      collapseClaimedYears({
        ...SUGGESTION,
        inProduction: true,
        yearTo: null,
        yearRanges: [{ from: 2019, to: null }],
      }),
    ).toEqual({ yearFrom: 2019, yearTo: null });
  });

  it("collapses several claimed ranges to their earliest start and latest end", () => {
    expect(
      collapseClaimedYears({
        ...SUGGESTION,
        yearRanges: [
          { from: 2019, to: 2023 },
          { from: 2024, to: null },
        ],
        inProduction: true,
      }),
    ).toEqual({ yearFrom: 2019, yearTo: null });
  });

  it("formats a single claimed range and every entry of a multi-range claim", () => {
    expect(formatClaimedYears(i18n.t, SUGGESTION)).toBeTruthy();
    expect(
      formatClaimedYears(i18n.t, {
        ...SUGGESTION,
        yearRanges: [
          { from: 2019, to: 2023 },
          { from: 2024, to: null },
        ],
      }),
    ).toContain("·");
  });

  it("joins claimed type codes with a slash", () => {
    expect(formatClaimedTypeCodes({ ...SUGGESTION, typeCodes: ["K50", "K51"] })).toBe(
      "K50/K51",
    );
  });

  it("unions claimed type codes into the current chips, capping at 8 and dropping duplicates", () => {
    expect(unionTypeCodes(["K50"], ["K50", "K51"])).toEqual({
      codes: ["K50", "K51"],
      capped: false,
    });

    const eight = ["A", "B", "C", "D", "E", "F", "G", "H"];

    expect(unionTypeCodes(eight, ["I"])).toEqual({ codes: eight, capped: true });
  });
});

describe("D6 boundary — the claim is never customer-facing (ui-spec §2.1)", () => {
  it("keeps `suggestion` off the customer catalogue-model type at compile time", () => {
    function readSuggestion(detail: CatalogueModelDetail) {
      // @ts-expect-error — `suggestion` must never be a member of the customer
      // catalogue-model type; this line existing without a type error is the bug.
      return detail.suggestion;
    }

    expect(readSuggestion).toBeInstanceOf(Function);
  });

  it("is imported by ModelIdentityPanel only, within frontend/src/components", () => {
    // No Node builtins (zero new dependencies, and this project's `types`
    // config does not carry `node`): every sibling `.tsx` source is read as
    // raw text through Vite's own `import.meta.glob`, already typed via
    // `vite/client`.
    const files = import.meta.glob<string>("./*.tsx", {
      query: "?raw",
      import: "default",
      eager: true,
    });

    const importers = Object.entries(files)
      .filter(([modulePath]) => modulePath !== "./ModelClaimPanel.tsx")
      .filter(([modulePath]) => !modulePath.endsWith(".test.tsx"))
      .filter(([, contents]) => /from ["']\.\/ModelClaimPanel["']/.test(contents))
      .map(([modulePath]) => modulePath.replace(/^\.\//, ""));

    expect(importers).toEqual(["ModelIdentityPanel.tsx"]);
  });
});
