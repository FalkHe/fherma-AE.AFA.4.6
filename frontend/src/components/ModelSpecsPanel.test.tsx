import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DraftSpec } from "../hooks/useProductReview";
import type { Product } from "../hooks/useProducts";
import { renderWithProviders } from "../test/render";

import { ModelSpecsPanel } from "./ModelSpecsPanel";

/**
 * These tests own the form's Zod schema, which is the one piece of validation
 * logic in this phase's UI: an emptied field must save as `null` (unknown is a
 * legitimate value — the extraction contract is "leave unknown fields null"),
 * and an impossible value must never reach the API.
 *
 * The save mutation is doubled so the transformed payload is observable; the
 * rest of the panel runs for real.
 */

const save = {
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  reset: vi.fn(),
};

vi.mock("../hooks/useProductReview", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../hooks/useProductReview")>();

  return { ...actual, useSaveDraftSpec: () => save };
});

const DRAFT_SPEC: DraftSpec = {
  category: "naked",
  engineCc: 599,
  cylinders: 4,
  powerKw: 72,
  torqueNm: null,
  wetWeightKg: 209,
  seatHeightMm: 785,
  tankCapacityL: 16.5,
  topSpeedKmh: null,
  abs: false,
  a2Eligible: null,
  priceBand: "budget",
  msrpEur: null,
  extra: { frame: "Steel tube" },
  sourceHints: null,
  extractedAt: "2026-08-25T09:12:00Z",
};

const PRODUCT: Product = {
  id: "01PRODUCTINREVIEW000000001",
  name: "Suzuki GSR 600",
  slug: "suzuki-gsr-600",
  manufacturer: "Suzuki",
  modelName: "GSR 600",
  yearFrom: 2006,
  yearTo: 2011,
  status: "in_review",
  draftSpec: DRAFT_SPEC,
  verifiedSpec: null,
  createdAt: "2026-08-25T09:03:00Z",
  updatedAt: "2026-08-25T09:14:00Z",
  queryName: "Suzuki GSR 600",
  buildingline: null,
  typeCodes: [],
  variants: [],
  suggestion: null,
};

function renderPanel(product: Product = PRODUCT) {
  return renderWithProviders(
    <ModelSpecsPanel product={product} onDirtyChange={() => undefined} />,
  );
}

/** The payload of the single save call, as the schema transformed it. */
function savedValues(): Partial<DraftSpec> {
  expect(save.mutate).toHaveBeenCalledTimes(1);

  return (save.mutate.mock.calls[0][0] as { values: Partial<DraftSpec> }).values;
}

beforeEach(() => {
  save.mutate.mockClear();
});

describe("ModelSpecsPanel", () => {
  it("saves an emptied number field as null, unknown selects included", async () => {
    renderPanel();

    const engineCc = screen.getByLabelText("Engine displacement");

    await userEvent.clear(engineCc);
    await userEvent.click(screen.getByRole("button", { name: "Save draft" }));

    const values = savedValues();

    // Emptied, not zeroed: the field is genuinely unknown again.
    expect(values.engineCc).toBeNull();
    // Untouched fields still travel with the request (full-object replace).
    expect(values.powerKw).toBe(72);
    expect(values.wetWeightKg).toBe(209);
    // The three-state select keeps "unknown" as null rather than false.
    expect(values.a2Eligible).toBeNull();
    expect(values.priceBand).toBe("budget");
    expect(values.category).toBe("naked");
  });

  it("rejects a negative number instead of sending it", async () => {
    renderPanel();

    const powerKw = screen.getByLabelText("Power");

    await userEvent.clear(powerKw);
    await userEvent.type(powerKw, "-5");
    await userEvent.click(screen.getByRole("button", { name: "Save draft" }));

    expect(await screen.findByText("Enter a positive number.")).toBeInTheDocument();
    expect(save.mutate).not.toHaveBeenCalled();
  });

  it("keeps save and discard disabled until something changes", async () => {
    renderPanel();

    expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Discard changes" })).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Torque"), "63");

    expect(screen.getByRole("button", { name: "Save draft" })).toBeEnabled();

    // Discarding restores the fetched draft and disables both buttons again.
    await userEvent.click(screen.getByRole("button", { name: "Discard changes" }));

    expect(screen.getByLabelText("Torque")).toHaveValue(null);
    expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled();
  });

  it("renders the verified specification read-only for a published model", () => {
    renderPanel({
      ...PRODUCT,
      status: "approved",
      draftSpec: null,
      verifiedSpec: { ...DRAFT_SPEC, a2Eligible: true },
    });

    expect(screen.getByText("Verified specification")).toBeInTheDocument();
    expect(screen.getByText("599 cc")).toBeInTheDocument();
    // A null value reads as unknown, not as an empty cell.
    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
  });
});
