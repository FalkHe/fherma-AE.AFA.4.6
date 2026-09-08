// UI-1 … UI-12 (ui-spec.md §12, §3.1, §6.1). Rendered through the real guard
// (`RequireAnonymous` behind `/signin`) via `renderApp`, so a request the
// guard itself makes (`GET /api/v1/users/me`) is always stubbed first.
import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderApp } from "../../../test/render";
import { deferredResponse, getRequests, mockRoute } from "../../../test/network";

const copy = {
  heading: "Sign in",
  invalidCredentials: "That username and password do not match. Please try again.",
  submitting: "Signing in…",
  networkError: "Cannot reach the server. Check your connection and try again.",
  unexpectedError: "Something went wrong. Please try again.",
  requiredUsername: "Enter a username.",
  requiredPassword: "Enter a password.",
};

function stubAnonymousSession() {
  mockRoute("GET", "/api/v1/users/me", {
    status: 401,
    body: { error: { code: "NOT_AUTHENTICATED", message: "Authentication required.", details: null } },
  });
}

function stubSignInSuccess(username = "thorin") {
  mockRoute("POST", "/api/v1/auth/sign-in", {
    status: 200,
    body: { id: "9f1c0b6a-6f7c-4a2f-9a3e-0b6d1c2e3f40", username, createdAt: "2026-09-08T12:34:56.789012+00:00" },
    headers: { "X-CSRF-Token": "csrf-token-value" },
  });
}

async function fillAndGetFields() {
  const username = screen.getByRole("textbox", { name: /username/i });
  const password = screen.getByLabelText(/password/i);
  return { username, password };
}

describe("SignInRoute (UI-1 … UI-12)", () => {
  beforeEach(() => {
    stubAnonymousSession();
  });

  it("UI-1: renders one h1 'Sign in', both fields, a submit button and a link to /signup", async () => {
    renderApp(["/signin"]);
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(copy.heading));
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("textbox", { name: /username/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /create an account/i })).toHaveAttribute("href", "/signup");
  });

  it("UI-2: Username has autocomplete=username; Password is type=password with autocomplete=current-password", async () => {
    renderApp(["/signin"]);
    const { username, password } = await waitFor(() => fillAndGetFields());
    expect(username).toHaveAttribute("autocomplete", "username");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "current-password");
  });

  it("UI-3: Username receives focus on mount", async () => {
    renderApp(["/signin"]);
    const { username } = await waitFor(() => fillAndGetFields());
    expect(username).toHaveFocus();
  });

  it("UI-4: submitting both fields empty sends no request, marks both invalid, and focuses Username", async () => {
    renderApp(["/signin"]);
    const { username, password } = await waitFor(() => fillAndGetFields());
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(getRequests({ method: "POST", path: "/api/v1/auth/sign-in" })).toHaveLength(0);
    expect(username).toHaveAttribute("aria-invalid", "true");
    expect(password).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(copy.requiredUsername)).toBeInTheDocument();
    expect(screen.getByText(copy.requiredPassword)).toBeInTheDocument();
    expect(username).toHaveFocus();
  });

  it("UI-5: applies no length or charset validation — a one-character username submits", async () => {
    stubSignInSuccess();
    renderApp(["/signin"]);
    const { username, password } = await waitFor(() => fillAndGetFields());
    const user = userEvent.setup();

    await user.type(username, "a");
    await user.type(password, "x");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(getRequests({ method: "POST", path: "/api/v1/auth/sign-in" })).toHaveLength(1));
  });

  it("UI-6: pressing Enter in the password field submits the form", async () => {
    stubSignInSuccess();
    renderApp(["/signin"]);
    const { username, password } = await waitFor(() => fillAndGetFields());
    const user = userEvent.setup();

    await user.type(username, "thorin");
    await user.type(password, "hunter-of-orcs{Enter}");

    await waitFor(() => expect(getRequests({ method: "POST", path: "/api/v1/auth/sign-in" })).toHaveLength(1));
  });

  it("UI-7: while in flight, the submit button is disabled and reads 'Signing in…', and both fields are disabled", async () => {
    const pending = deferredResponse();
    mockRoute("POST", "/api/v1/auth/sign-in", () => pending.promise);
    renderApp(["/signin"]);
    const { username, password } = await waitFor(() => fillAndGetFields());
    const user = userEvent.setup();

    await user.type(username, "thorin");
    await user.type(password, "hunter-of-orcs");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: copy.submitting })).toBeDisabled());
    expect(username).toBeDisabled();
    expect(password).toBeDisabled();

    pending.resolve({
      status: 200,
      body: { id: "9f1c0b6a-6f7c-4a2f-9a3e-0b6d1c2e3f40", username: "thorin", createdAt: "2026-09-08T12:34:56.789012+00:00" },
      headers: { "X-CSRF-Token": "csrf-token-value" },
    });
  });

  it("UI-8 / UI-9: a 401 shows exactly one alert with the shared invalid-credentials copy, keeps Username, clears Password, and marks neither field invalid", async () => {
    mockRoute("POST", "/api/v1/auth/sign-in", {
      status: 401,
      body: { error: { code: "INVALID_CREDENTIALS", message: "SERVER_RAW_MESSAGE_NOT_FOR_DISPLAY", details: null } },
    });
    renderApp(["/signin"]);
    const { username, password } = await waitFor(() => fillAndGetFields());
    const user = userEvent.setup();

    await user.type(username, "nobody");
    await user.type(password, "wrong-password");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    const alerts = await screen.findAllByRole("alert");
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent(copy.invalidCredentials);
    expect(screen.queryByText(/SERVER_RAW_MESSAGE/)).not.toBeInTheDocument();

    expect(username).toHaveValue("nobody");
    expect(password).toHaveValue("");
    expect(username).not.toHaveAttribute("aria-invalid", "true");
    expect(password).not.toHaveAttribute("aria-invalid", "true");
  });

  it("UI-10: a network failure shows the network copy and preserves both values", async () => {
    mockRoute("POST", "/api/v1/auth/sign-in", () => {
      throw new Error("simulated network failure");
    });
    renderApp(["/signin"]);
    const { username, password } = await waitFor(() => fillAndGetFields());
    const user = userEvent.setup();

    await user.type(username, "thorin");
    await user.type(password, "hunter-of-orcs");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(copy.networkError);
    expect(username).toHaveValue("thorin");
    expect(password).toHaveValue("hunter-of-orcs");
  });

  it.each([422, 500])("UI-10: a %i shows the unexpected-error copy and preserves both values", async (status) => {
    mockRoute("POST", "/api/v1/auth/sign-in", {
      status,
      body: { error: { code: status === 422 ? "VALIDATION_ERROR" : "INTERNAL_ERROR", message: "x", details: null } },
    });
    renderApp(["/signin"]);
    const { username, password } = await waitFor(() => fillAndGetFields());
    const user = userEvent.setup();

    await user.type(username, "thorin");
    await user.type(password, "hunter-of-orcs");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(copy.unexpectedError);
    expect(username).toHaveValue("thorin");
    expect(password).toHaveValue("hunter-of-orcs");
  });

  it("UI-11: after a failed submit, focus is on the alert and Tab from there reaches Username", async () => {
    mockRoute("POST", "/api/v1/auth/sign-in", {
      status: 401,
      body: { error: { code: "INVALID_CREDENTIALS", message: "x", details: null } },
    });
    renderApp(["/signin"]);
    const { username, password } = await waitFor(() => fillAndGetFields());
    const user = userEvent.setup();

    await user.type(username, "thorin");
    await user.type(password, "wrong");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    const alert = await screen.findByRole("alert");
    await waitFor(() => expect(alert).toHaveFocus());

    await user.tab();
    expect(username).toHaveFocus();
  });

  it("UI-12: on success, navigates to / via replace and moves focus to the greeting, which is the home h1", async () => {
    stubSignInSuccess("thorin");
    const app = renderApp(["/signin"]);
    const { username, password } = await waitFor(() => fillAndGetFields());
    const user = userEvent.setup();

    await user.type(username, "thorin");
    await user.type(password, "hunter-of-orcs");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(app.getPathname()).toBe("/"));
    const heading = await screen.findByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("thorin");
    await waitFor(() => expect(heading).toHaveFocus());

    // replace: nothing precedes the sign-in entry once it is overwritten, so
    // "back" cannot resurrect it.
    app.goBack();
    await waitFor(() => expect(app.getPathname()).toBe("/"));
    expect(screen.queryByRole("heading", { name: copy.heading })).not.toBeInTheDocument();
  });
});
