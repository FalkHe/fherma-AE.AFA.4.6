// Behaviour that used to be asserted indirectly through
// modules/home/routes/HomeRoute.test.tsx (UI-23/UI-24/UI-42: the bar is a
// banner landmark, the wordmark is not a heading) moves here now that
// `AppShell` is its own `core/` component with no module caller of its own
// (sprint 007/04 WI2). The wordmark comes from `common:app.title` — no
// `title` prop exists anymore.
//
// This deliberately does not use `../../test/render`'s `renderWithProviders`:
// that helper imports `App`, which — until a later work item rewires it —
// still imports the old `modules/home/components/AppShell` path this sprint
// deletes, so pulling it in here would fail for a reason unrelated to this
// component. A local, minimal provider stack (theme + i18n only, no router,
// no query client) is all `AppShell` itself needs.
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { I18nextProvider } from "react-i18next";

import { theme } from "../theme";
import i18n from "../i18n";
import { AppShell } from "./AppShell";

function Providers({ children }: { children: ReactElement }) {
  return (
    <ThemeProvider theme={theme} noSsr defaultMode="dark">
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    </ThemeProvider>
  );
}

function renderAppShell(ui: ReactElement) {
  return render(ui, { wrapper: ({ children }) => <Providers>{children as ReactElement}</Providers> });
}

describe("AppShell", () => {
  it("renders the product name from common:app.title as branding, not a heading", () => {
    renderAppShell(
      <AppShell>
        <p>content</p>
      </AppShell>,
    );

    const wordmark = screen.getByText("The Goblin's Tavern");
    expect(wordmark.tagName).toBe("P");
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });

  it("exposes the bar as a banner landmark", () => {
    renderAppShell(
      <AppShell>
        <p>content</p>
      </AppShell>,
    );

    expect(screen.getByRole("banner")).toBeInTheDocument();
  });

  it("renders the action slot beside the wordmark when passed, and nothing when omitted", () => {
    const { rerender } = renderAppShell(
      <AppShell action={<button type="button">Account</button>}>
        <p>content</p>
      </AppShell>,
    );

    expect(screen.getByRole("banner")).toContainElement(screen.getByRole("button", { name: "Account" }));

    rerender(
      <AppShell>
        <p>content</p>
      </AppShell>,
    );

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders children inside the main landmark", () => {
    renderAppShell(
      <AppShell>
        <p>page content</p>
      </AppShell>,
    );

    expect(screen.getByRole("main")).toHaveTextContent("page content");
  });
});
