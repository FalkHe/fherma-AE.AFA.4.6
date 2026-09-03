import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Route, Routes } from "react-router";

import { useAuth } from "../hooks/useAuth";
import { jsonResponse, stubFetch } from "../test/network";
import { renderWithProviders } from "../test/render";

import { RegisterRoute } from "./RegisterRoute";

/**
 * Coverage for the registration screen: the client-side rules (submit-only,
 * first invalid field focused — none of these ever reach the network), the
 * server-rejection mapping (409 taken username, 422 field-level disagreement),
 * a network failure, and the success path (auth cache + navigation).
 *
 * Server-driven field errors are asserted on their rendered text only, not on
 * focus: `handleServerError` focuses synchronously inside the mutation's
 * `onError`, while the field is still `disabled` from the pending submit (the
 * same class of timing issue `LoginRoute.test.tsx` documents) — the outline
 * for this step only asks for the client-rule cases to prove focus.
 */

/** `GET /auth/me` answered as "nobody is signed in", the default for these tests. */
function anonymousMe(): Response {
  return jsonResponse({ detail: "Not authenticated." }, { status: 401 });
}

/** A component that surfaces the cached identity, to prove a successful register updates it. */
function Home() {
  const { user } = useAuth();

  return <div>Home for {user?.username ?? "nobody"}</div>;
}

function renderRegisterRoute() {
  return renderWithProviders(
    <Routes>
      <Route path="/register" element={<RegisterRoute />} />
      <Route path="/" element={<Home />} />
    </Routes>,
    { initialEntries: ["/register"] },
  );
}

function fields() {
  return {
    // `required` renders a trailing " *" inside the label's text content, so an
    // exact string match (as the visible label reads) misses; `LoginRoute.
    // test.tsx` sidesteps the same thing with a regex. "Confirm password"
    // starts differently, so `/^Password/` cannot also match it.
    username: screen.getByLabelText(/^Username/),
    password: screen.getByLabelText(/^Password/),
    confirmPassword: screen.getByLabelText(/^Confirm password/),
    submit: screen.getByRole("button", { name: "Create account" }),
  };
}

describe("RegisterRoute", () => {
  describe("client-side validation (submit-only)", () => {
    it("rejects a too-short username and focuses it", async () => {
      stubFetch(async (request) =>
        new URL(request.url).pathname === "/auth/me" ? anonymousMe() : anonymousMe(),
      );
      const user = userEvent.setup();
      renderRegisterRoute();
      const { username, password, confirmPassword, submit } = fields();

      // No complaint before the first submit attempt.
      expect(screen.queryByText("Use 3–32 characters: letters, digits, . _ -")).not.toBeInTheDocument();

      await user.type(username, "ab");
      await user.type(password, "longenough1");
      await user.type(confirmPassword, "longenough1");
      await user.click(submit);

      expect(await screen.findByText("Use 3–32 characters: letters, digits, . _ -")).toBeInTheDocument();
      expect(username).toHaveFocus();
    });

    it("rejects a username with a disallowed character and focuses it", async () => {
      stubFetch(async () => anonymousMe());
      const user = userEvent.setup();
      renderRegisterRoute();
      const { username, password, confirmPassword, submit } = fields();

      await user.type(username, "abc def");
      await user.type(password, "longenough1");
      await user.type(confirmPassword, "longenough1");
      await user.click(submit);

      expect(await screen.findByText("Use 3–32 characters: letters, digits, . _ -")).toBeInTheDocument();
      expect(username).toHaveFocus();
    });

    it("rejects a too-short password and focuses it", async () => {
      stubFetch(async () => anonymousMe());
      const user = userEvent.setup();
      renderRegisterRoute();
      const { username, password, confirmPassword, submit } = fields();

      await user.type(username, "validuser");
      await user.type(password, "short1");
      await user.type(confirmPassword, "short1");
      await user.click(submit);

      expect(
        await screen.findByText("Password must be at least 8 characters."),
      ).toBeInTheDocument();
      expect(password).toHaveFocus();
    });

    it("rejects a mismatched confirmation and focuses it", async () => {
      stubFetch(async () => anonymousMe());
      const user = userEvent.setup();
      renderRegisterRoute();
      const { username, password, confirmPassword, submit } = fields();

      await user.type(username, "validuser");
      await user.type(password, "longenough1");
      await user.type(confirmPassword, "different1");
      await user.click(submit);

      expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
      expect(confirmPassword).toHaveFocus();
    });
  });

  describe("server rejections", () => {
    it("maps a 409 to the username field", async () => {
      stubFetch(async (request) => {
        const url = new URL(request.url);

        if (url.pathname === "/auth/me") {
          return anonymousMe();
        }
        if (url.pathname === "/auth/register" && request.method === "POST") {
          return jsonResponse({ detail: "Username is already taken." }, { status: 409 });
        }
        throw new Error(`unexpected request ${request.method} ${url.pathname}`);
      });
      const user = userEvent.setup();
      renderRegisterRoute();
      const { username, password, confirmPassword, submit } = fields();

      await user.type(username, "validuser");
      await user.type(password, "longenough1");
      await user.type(confirmPassword, "longenough1");
      await user.click(submit);

      expect(
        await screen.findByText("This username is already taken."),
      ).toBeInTheDocument();
    });

    it("maps a 422 naming the username field to the client-rule copy", async () => {
      stubFetch(async (request) => {
        const url = new URL(request.url);

        if (url.pathname === "/auth/me") {
          return anonymousMe();
        }
        if (url.pathname === "/auth/register" && request.method === "POST") {
          return jsonResponse(
            {
              detail: [
                {
                  loc: ["body", "username"],
                  msg: "String should have at least 3 characters",
                  type: "string_too_short",
                },
              ],
            },
            { status: 422 },
          );
        }
        throw new Error(`unexpected request ${request.method} ${url.pathname}`);
      });
      const user = userEvent.setup();
      renderRegisterRoute();
      // A username the client accepts but the server (hypothetically) rejects.
      const { username, password, confirmPassword, submit } = fields();

      await user.type(username, "validuser");
      await user.type(password, "longenough1");
      await user.type(confirmPassword, "longenough1");
      await user.click(submit);

      expect(await screen.findByText("Use 3–32 characters: letters, digits, . _ -")).toBeInTheDocument();
    });

    it("maps a 422 naming the password field to the client-rule copy", async () => {
      stubFetch(async (request) => {
        const url = new URL(request.url);

        if (url.pathname === "/auth/me") {
          return anonymousMe();
        }
        if (url.pathname === "/auth/register" && request.method === "POST") {
          return jsonResponse(
            {
              detail: [
                {
                  loc: ["body", "password"],
                  msg: "String should have at least 8 characters",
                  type: "string_too_short",
                },
              ],
            },
            { status: 422 },
          );
        }
        throw new Error(`unexpected request ${request.method} ${url.pathname}`);
      });
      const user = userEvent.setup();
      renderRegisterRoute();
      const { username, password, confirmPassword, submit } = fields();

      await user.type(username, "validuser");
      await user.type(password, "longenough1");
      await user.type(confirmPassword, "longenough1");
      await user.click(submit);

      expect(
        await screen.findByText("Password must be at least 8 characters."),
      ).toBeInTheDocument();
    });

    it("shows the general error alert when the register call fails at the network level", async () => {
      stubFetch(async (request) => {
        const url = new URL(request.url);

        if (url.pathname === "/auth/me") {
          return anonymousMe();
        }
        if (url.pathname === "/auth/register" && request.method === "POST") {
          throw new Error("network request failed");
        }
        throw new Error(`unexpected request ${request.method} ${url.pathname}`);
      });
      const user = userEvent.setup();
      renderRegisterRoute();
      const { username, password, confirmPassword, submit } = fields();

      await user.type(username, "validuser");
      await user.type(password, "longenough1");
      await user.type(confirmPassword, "longenough1");
      await user.click(submit);

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Something went wrong. Please try again.",
      );
    });
  });

  it("registers, signs in and navigates on success", async () => {
    stubFetch(async (request) => {
      const url = new URL(request.url);

      if (url.pathname === "/auth/me") {
        return anonymousMe();
      }
      if (url.pathname === "/auth/register" && request.method === "POST") {
        return jsonResponse(
          { id: "01REGISTERED0000000000000", username: "validuser", role: "user" },
          { status: 201 },
        );
      }
      if (url.pathname === "/auth/login" && request.method === "POST") {
        return jsonResponse(
          { id: "01REGISTERED0000000000000", username: "validuser", role: "user" },
          { status: 200 },
        );
      }
      throw new Error(`unexpected request ${request.method} ${url.pathname}`);
    });
    const user = userEvent.setup();
    renderRegisterRoute();
    const { username, password, confirmPassword, submit } = fields();

    await user.type(username, "validuser");
    await user.type(password, "longenough1");
    await user.type(confirmPassword, "longenough1");
    await user.click(submit);

    expect(await screen.findByText("Home for validuser")).toBeInTheDocument();
  });
});
