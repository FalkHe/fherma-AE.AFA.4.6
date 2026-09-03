import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { jsonResponse, stubFetch } from "../test/network";
import { renderWithProviders } from "../test/render";

import { AddModelDialog } from "./AddModelDialog";

/**
 * The dialog talks to `POST /api/products` through the stubbed `fetch`. Its error
 * branches are keyed on the status code alone (409 duplicate, 422 validation),
 * never on the server's `detail` sentence — hence the JSON:API error bodies here.
 */
function renderDialog() {
  const onClose = vi.fn();
  const onCreated = vi.fn();

  renderWithProviders(<AddModelDialog onClose={onClose} onCreated={onCreated} />);

  return {
    onClose,
    onCreated,
    nameField: screen.getByRole("textbox", { name: /Model name/ }),
    submit: screen.getByRole("button", { name: "Add & start ingestion" }),
  };
}

/** A created `backlog` row, as `POST /api/products` answers it. */
function createdResponse() {
  return jsonResponse(
    {
      data: {
        id: "01PRODUCTCREATED00000000001",
        type: "products",
        attributes: {
          name: "Triumph Trident 660",
          slug: "triumph-trident-660",
          manufacturer: null,
          modelName: null,
          yearFrom: null,
          yearTo: null,
          status: "backlog",
          draftSpec: null,
          verifiedSpec: null,
          createdAt: "2026-08-26T10:00:00Z",
          updatedAt: "2026-08-26T10:00:00Z",
        },
      },
    },
    { status: 201 },
  );
}

describe("AddModelDialog", () => {
  it("rejects a blank name on submit without calling the server", async () => {
    const requests: string[] = [];

    stubFetch((request) => {
      requests.push(request.url);

      return createdResponse();
    });

    const { nameField, submit, onCreated } = renderDialog();

    await userEvent.type(nameField, "   ");
    await userEvent.click(submit);

    expect(screen.getByText("Enter a model name.")).toBeInTheDocument();
    expect(requests).toEqual([]);
    expect(onCreated).not.toHaveBeenCalled();
    // Still interactive: nothing was submitted.
    expect(submit).toBeEnabled();
  });

  it("reports a duplicate model on the name field", async () => {
    stubFetch(() =>
      jsonResponse(
        {
          errors: [
            {
              status: "409",
              code: "duplicate-model",
              detail: "A motorbike with slug honda-cb500f already exists.",
            },
          ],
        },
        { status: 409 },
      ),
    );

    const { nameField, submit, onCreated } = renderDialog();

    await userEvent.type(nameField, "Honda CB500F");
    await userEvent.click(submit);

    expect(
      await screen.findByText("This model is already in the catalogue."),
    ).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
    // The typed value survives, so a correction costs no retyping.
    expect(nameField).toHaveValue("Honda CB500F");
  });

  it("shows the server error for a 5xx and keeps the typed value", async () => {
    stubFetch(() => jsonResponse({ detail: "boom" }, { status: 500 }));

    const { nameField, submit, onCreated } = renderDialog();

    await userEvent.type(nameField, "Triumph Trident 660");
    await userEvent.click(submit);

    expect(
      await screen.findByText("Something went wrong. Please try again."),
    ).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
    expect(nameField).toHaveValue("Triumph Trident 660");
  });

  it("disables the form while the creation is in flight and reports success", async () => {
    // The response is held back so the pending state stays observable.
    let release!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      release = resolve;
    });

    stubFetch(() => pending);

    const { nameField, submit, onCreated, onClose } = renderDialog();

    await userEvent.type(nameField, "Triumph Trident 660");
    await userEvent.click(submit);

    expect(submit).toBeDisabled();
    expect(nameField).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();

    await act(async () => {
      release(createdResponse());
      await pending;
    });

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledTimes(1);
    });
    // Closing is the caller's job (it also clears the status filter).
    expect(onClose).not.toHaveBeenCalled();
  });
});
