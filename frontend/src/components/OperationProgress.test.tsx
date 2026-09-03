import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Operation } from "../hooks/useOperations";
import { renderWithProviders } from "../test/render";

import { OperationProgress } from "./OperationProgress";

/**
 * The graded progress indicator: one component covers queued, running,
 * finished and failed, so the state matrix is what this file asserts.
 */
function operation(
  overrides: Partial<Pick<Operation, "status" | "progress" | "message">>,
): Pick<Operation, "status" | "progress" | "message"> {
  return { status: "running", progress: 40, message: null, ...overrides };
}

const NAME = "Suzuki GSR 600";

describe("OperationProgress", () => {
  it("announces an indeterminate bar while the job is queued", () => {
    renderWithProviders(
      <OperationProgress operation={operation({ status: "queued", progress: 0 })} name={NAME} />,
    );

    const bar = screen.getByRole("progressbar", {
      name: "Ingestion progress for Suzuki GSR 600",
    });

    // Indeterminate: no value is known yet, so MUI exposes none.
    expect(bar).not.toHaveAttribute("aria-valuenow");
    expect(screen.getByText("Queued…")).toBeInTheDocument();
  });

  it("shows percentage and the server's message while running", () => {
    renderWithProviders(
      <OperationProgress
        operation={operation({ message: "Fetching sources (2/6)" })}
        name={NAME}
      />,
    );

    expect(
      screen.getByRole("progressbar", { name: "Ingestion progress for Suzuki GSR 600" }),
    ).toHaveAttribute("aria-valuenow", "40");
    // The message is server-generated English, rendered verbatim next to the
    // translated percentage.
    expect(screen.getByText("40% — Fetching sources (2/6)")).toBeInTheDocument();
  });

  it("renders nothing once the job succeeded", () => {
    const { container } = renderWithProviders(
      <OperationProgress
        operation={operation({ status: "succeeded", progress: 100 })}
        name={NAME}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("reports a failure with its message and no progress bar", () => {
    renderWithProviders(
      <OperationProgress
        operation={operation({
          status: "failed",
          progress: 15,
          message: "No usable sources could be retrieved",
        })}
        name={NAME}
      />,
    );

    expect(
      screen.getByText("Ingestion failed — No usable sources could be retrieved"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("offers a retry control on a failure only when the caller supplies one", async () => {
    const onRetry = vi.fn();

    const { unmount } = renderWithProviders(
      <OperationProgress operation={operation({ status: "failed" })} name={NAME} />,
    );

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    unmount();

    renderWithProviders(
      <OperationProgress
        operation={operation({ status: "failed" })}
        name={NAME}
        onRetry={onRetry}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Retry ingestion" }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
