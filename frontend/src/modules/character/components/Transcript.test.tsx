// Creation-chat viewport fix — the transcript well's own scroll behaviour.
// jsdom does no layout, so each test pins the well's scroll geometry with
// `Object.defineProperty` on the `log` element itself and drives it with a
// real `scroll` event, the same signal a browser sends.
import { describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../../test/render";
import character from "../../../core/i18n/locales/en/character.json";
import type { ChatTurn } from "../hooks/useCreationChat";
import { Transcript } from "./Transcript";

const TURNS: ChatTurn[] = [
  { speaker: "keeper", text: "Well met. Take her, or make your own?" },
  { speaker: "player", text: "Make my own" },
  { speaker: "keeper", text: "A fine choice. Race and class?" },
];

function pinGeometry(el: HTMLElement, { scrollTop }: { scrollTop: number }) {
  Object.defineProperty(el, "scrollHeight", { configurable: true, value: 1000 });
  Object.defineProperty(el, "clientHeight", { configurable: true, value: 300 });
  Object.defineProperty(el, "scrollTop", { configurable: true, writable: true, value: scrollTop });
}

describe("Transcript", () => {
  it("renders the turns inside a labelled log, with no jump pill while at the bottom", () => {
    renderWithProviders(<Transcript turns={TURNS} failed={false} onRetry={() => {}} />);

    const log = screen.getByRole("log", { name: character.chat.transcript });
    expect(log).toHaveTextContent("A fine choice. Race and class?");
    expect(screen.queryByRole("button", { name: character.chat.jumpToLatest })).not.toBeInTheDocument();
  });

  it("shows the jump pill after a scroll up, and clicking it returns to the bottom and hides it", async () => {
    renderWithProviders(<Transcript turns={TURNS} failed={false} onRetry={() => {}} />);
    const log = screen.getByRole("log", { name: character.chat.transcript });

    // Still within the 48px threshold: counts as the bottom.
    pinGeometry(log, { scrollTop: 680 });
    fireEvent.scroll(log);
    expect(screen.queryByRole("button", { name: character.chat.jumpToLatest })).not.toBeInTheDocument();

    pinGeometry(log, { scrollTop: 200 });
    fireEvent.scroll(log);
    const pill = await screen.findByRole("button", { name: character.chat.jumpToLatest });

    await userEvent.setup().click(pill);

    expect(log.scrollTop).toBe(1000);
    expect(screen.queryByRole("button", { name: character.chat.jumpToLatest })).not.toBeInTheDocument();
  });

  it("keeps the failed turn as an alert and offers a retry", () => {
    renderWithProviders(<Transcript turns={TURNS} failed onRetry={() => {}} />);

    expect(screen.getByRole("alert")).toHaveTextContent("A fine choice. Race and class?");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
