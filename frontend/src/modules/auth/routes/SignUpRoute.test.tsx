// UI-13 … UI-20 (ui-spec.md §12, §3.2, §6.2), plus step-0.1.md criteria 34
// and 35 (lower-cased greeting, never the server's raw message).
import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderApp } from "../../../test/render";
import { getRequests, mockRoute } from "../../../test/network";
import { PASSWORD_MIN, USERNAME_MAX, USERNAME_MIN } from "../validation";

const copy = {
  heading: "Create an account",
  usernameHint: `${USERNAME_MIN}–${USERNAME_MAX} characters. Letters, numbers, underscore and hyphen only.`,
  passwordHint: `At least ${PASSWORD_MIN} characters.`,
  usernameTaken: "That username is already taken. Please choose another.",
  tooShortUsername: `Use at least ${USERNAME_MIN} characters.`,
};

function stubAnonymousSession() {
  mockRoute("GET", "/api/v1/users/me", {
    status: 401,
    body: { error: { code: "NOT_AUTHENTICATED", message: "Authentication required.", details: null } },
  });
}

function stubRegisterSuccess(username: string) {
  mockRoute("POST", "/api/v1/auth/register", {
    status: 201,
    body: { id: "9f1c0b6a-6f7c-4a2f-9a3e-0b6d1c2e3f40", username, createdAt: "2026-09-08T12:34:56.789012+00:00" },
    headers: { "X-CSRF-Token": "csrf-token-value" },
  });
}

async function getFields() {
  return {
    username: screen.getByRole("textbox", { name: /username/i }),
    password: screen.getByLabelText(/password/i),
  };
}

describe("SignUpRoute (UI-13 … UI-20)", () => {
  beforeEach(() => {
    stubAnonymousSession();
  });

  it("UI-13: renders one h1 'Create an account', both fields, a submit button and a link to /signin", async () => {
    renderApp(["/signup"]);
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(copy.heading));
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^sign in$/i })).toHaveAttribute("href", "/signin");
  });

  it("UI-14: Password has autocomplete=new-password; no confirm-password field and no visibility toggle", async () => {
    renderApp(["/signup"]);
    await waitFor(() => getFields());
    const password = screen.getByLabelText(/password/i);
    expect(password).toHaveAttribute("autocomplete", "new-password");
    expect(document.querySelectorAll('input[type="password"]')).toHaveLength(1);
    // Only the submit button is a button on this screen — no icon-only toggle.
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("UI-15: both fields show their rule hint, derived from validation.ts, before any interaction", async () => {
    renderApp(["/signup"]);
    await waitFor(() => getFields());
    expect(screen.getByText(copy.usernameHint)).toBeInTheDocument();
    expect(screen.getByText(copy.passwordHint)).toBeInTheDocument();
  });

  it("UI-16 / UI-17: an untouched field shows no error; blur after edit shows one and it replaces the hint; typing clears it", async () => {
    renderApp(["/signup"]);
    const { username } = await waitFor(() => getFields());
    const user = userEvent.setup();

    expect(screen.queryByText(copy.tooShortUsername)).not.toBeInTheDocument();

    await user.type(username, "ab"); // below USERNAME_MIN
    await user.tab();

    expect(screen.getByText(copy.tooShortUsername)).toBeInTheDocument();
    expect(screen.queryByText(copy.usernameHint)).not.toBeInTheDocument(); // replaced, not appended
    expect(username).toHaveAttribute("aria-invalid", "true");

    await user.type(username, "c"); // still typing — cleared immediately, no re-validation mid-typing
    expect(screen.queryByText(copy.tooShortUsername)).not.toBeInTheDocument();
  });

  it("UI-18: a client-side-invalid submit sends no request and focuses the first invalid field", async () => {
    renderApp(["/signup"]);
    const { username } = await waitFor(() => getFields());
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(getRequests({ method: "POST", path: "/api/v1/auth/register" })).toHaveLength(0);
    expect(username).toHaveFocus();
  });

  it("UI-19 / 35: a 409 marks Username invalid with the mapped copy, keeps both values, focuses Username, and shows no form-level alert — never the server's raw message", async () => {
    mockRoute("POST", "/api/v1/auth/register", {
      status: 409,
      body: { error: { code: "USERNAME_TAKEN", message: "SERVER_RAW_MESSAGE_NOT_FOR_DISPLAY", details: null } },
    });
    renderApp(["/signup"]);
    const { username, password } = await waitFor(() => getFields());
    const user = userEvent.setup();

    await user.type(username, "aragorn");
    await user.type(password, "hunter-of-orcs");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(username).toHaveAttribute("aria-invalid", "true"));
    expect(screen.getByText(copy.usernameTaken)).toBeInTheDocument();
    expect(screen.queryByText(/SERVER_RAW_MESSAGE/)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(username).toHaveValue("aragorn");
    expect(password).toHaveValue("hunter-of-orcs");
    expect(username).toHaveFocus();
  });

  it("UI-20 / 34: on success lands on / via replace, already signed in, greeting shows the server's lower-cased username", async () => {
    stubRegisterSuccess("aragorn"); // server-normalised form of "Aragorn"
    const app = renderApp(["/signup"]);
    const { username, password } = await waitFor(() => getFields());
    const user = userEvent.setup();

    await user.type(username, "Aragorn");
    await user.type(password, "hunter-of-orcs");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(app.getPathname()).toBe("/"));
    expect(screen.queryByText(/account created/i)).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Welcome, aragorn.");

    app.goBack();
    await waitFor(() => expect(app.getPathname()).toBe("/"));
    expect(screen.queryByRole("heading", { name: copy.heading })).not.toBeInTheDocument();
  });
});
