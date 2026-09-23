// Sprint 010/06 WI3, I2 ← AC5. jsdom has no layout (research.md "Scrolling
// under test"): `scrollHeight`/`clientHeight` always read 0 and never
// clamp `scrollTop`, so the harness below defines them on the scrolling
// node itself — via a callback ref, so the override lands before the
// hook's own mount effect runs — and drives the rest through `scrollTop`
// plus a `scroll` event, exactly as the hook is meant to be driven.
import { type MutableRefObject, type ReactElement, type RefObject } from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { useStickToLatest } from "./useStickToLatest";

const SCROLL_HEIGHT = 1000;
const CLIENT_HEIGHT = 200;

function withFixedMetrics(ref: RefObject<HTMLDivElement | null>) {
  return (node: HTMLDivElement | null) => {
    (ref as MutableRefObject<HTMLDivElement | null>).current = node;
    if (node) {
      Object.defineProperty(node, "scrollHeight", { value: SCROLL_HEIGHT, configurable: true });
      Object.defineProperty(node, "clientHeight", { value: CLIENT_HEIGHT, configurable: true });
    }
  };
}

function Harness(): ReactElement {
  const { scrollRef, atBottom, jumpToLatest } = useStickToLatest();

  return (
    <div>
      <div data-testid="scroller" ref={withFixedMetrics(scrollRef)} />
      <div data-testid="state">{atBottom ? "bottom" : "scrolled-up"}</div>
      <button onClick={jumpToLatest}>jump</button>
    </div>
  );
}

describe("useStickToLatest", () => {
  it("starts at the newest entry", () => {
    render(<Harness />);

    const scroller = screen.getByTestId("scroller") as HTMLDivElement;
    expect(scroller.scrollTop).toBe(SCROLL_HEIGHT);
    expect(screen.getByTestId("state")).toHaveTextContent("bottom");
  });

  it("reports not-at-bottom once the reader scrolls up", () => {
    render(<Harness />);

    const scroller = screen.getByTestId("scroller") as HTMLDivElement;
    scroller.scrollTop = 100;
    fireEvent.scroll(scroller);

    expect(screen.getByTestId("state")).toHaveTextContent("scrolled-up");
  });

  it("reports at-bottom again once the reader scrolls back down", () => {
    render(<Harness />);

    const scroller = screen.getByTestId("scroller") as HTMLDivElement;
    scroller.scrollTop = 100;
    fireEvent.scroll(scroller);
    expect(screen.getByTestId("state")).toHaveTextContent("scrolled-up");

    scroller.scrollTop = SCROLL_HEIGHT - CLIENT_HEIGHT;
    fireEvent.scroll(scroller);

    expect(screen.getByTestId("state")).toHaveTextContent("bottom");
  });

  it("jumping returns to the newest entry", () => {
    render(<Harness />);

    const scroller = screen.getByTestId("scroller") as HTMLDivElement;
    scroller.scrollTop = 100;
    fireEvent.scroll(scroller);
    expect(screen.getByTestId("state")).toHaveTextContent("scrolled-up");

    fireEvent.click(screen.getByRole("button", { name: "jump" }));

    expect(scroller.scrollTop).toBe(SCROLL_HEIGHT);
    expect(screen.getByTestId("state")).toHaveTextContent("bottom");
  });

  it("keeps following new rows while the reader is at the newest entry", () => {
    render(<Harness />);
    const scroller = screen.getByTestId("scroller") as HTMLDivElement;
    expect(scroller.scrollTop).toBe(SCROLL_HEIGHT);

    // Simulate a new row streaming in: the transcript grows and a mutation
    // fires. Nothing forces `scrollTop` back to the (now stale) old value —
    // only the hook's own observer would push it to the new `scrollHeight`.
    Object.defineProperty(scroller, "scrollHeight", { value: SCROLL_HEIGHT + 400, configurable: true });
    scroller.appendChild(document.createElement("div"));

    return vi.waitFor(() => expect(scroller.scrollTop).toBe(SCROLL_HEIGHT + 400));
  });

  it("does not fight the reader once they have scrolled up", async () => {
    render(<Harness />);
    const scroller = screen.getByTestId("scroller") as HTMLDivElement;

    scroller.scrollTop = 100;
    fireEvent.scroll(scroller);
    expect(screen.getByTestId("state")).toHaveTextContent("scrolled-up");

    Object.defineProperty(scroller, "scrollHeight", { value: SCROLL_HEIGHT + 400, configurable: true });
    scroller.appendChild(document.createElement("div"));

    // Give any observer a chance to run, then assert it left `scrollTop` alone.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(scroller.scrollTop).toBe(100);
  });
});
