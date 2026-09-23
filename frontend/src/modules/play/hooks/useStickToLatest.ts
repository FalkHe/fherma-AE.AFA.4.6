// The transcript's stay-at-latest behaviour (D12 §2, sprint 010/06 WI3,
// I2 ← AC5): "The transcript keeps itself at the newest entry; scrolling
// up puts a Jump to the latest pill at the foot of it until the player
// scrolls back down." `Transcript.tsx` (WI2, built in parallel) puts
// `scrollRef` on its own scrolling element and renders `JumpToLatestPill`
// only while `!atBottom`.
//
// jsdom has no layout engine (research.md "Scrolling under test"):
// `IntersectionObserver` and `scrollIntoView` don't exist there, so this
// reads `scrollTop` against `scrollHeight`/`clientHeight` instead --
// something a test can drive directly by setting those properties and
// firing a `scroll` event.
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

// How close to the true bottom still counts as "at the newest entry" --
// wide enough to absorb the sub-pixel rounding a real browser's layout
// produces, without ever mistaking a genuine scroll-up for still being at
// the bottom.
const BOTTOM_THRESHOLD_PX = 24;

export interface UseStickToLatestResult {
  scrollRef: RefObject<HTMLDivElement | null>;
  atBottom: boolean;
  jumpToLatest: () => void;
}

function isAtBottom(el: HTMLElement): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_THRESHOLD_PX;
}

export function useStickToLatest(): UseStickToLatestResult {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);
  // Read inside the `MutationObserver` callback below, which fires outside
  // React's render cycle -- a plain `useState` value there would close over
  // whichever `atBottom` was current when the effect last ran, not the
  // latest one.
  const atBottomRef = useRef(true);

  const jumpToLatest = useCallback(() => {
    const el = scrollRef.current;
    if (!el) {
      return;
    }
    el.scrollTop = el.scrollHeight;
    atBottomRef.current = true;
    setAtBottom(true);
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) {
      return;
    }

    // Opens on the recorded transcript, scrolled to the newest entry (D12
    // §1.4/§2), before the reader sees anything else.
    el.scrollTop = el.scrollHeight;

    const handleScroll = () => {
      const bottom = isAtBottom(el);
      atBottomRef.current = bottom;
      setAtBottom(bottom);
    };
    el.addEventListener("scroll", handleScroll);

    // Rows stream in as a turn runs (D12 §1.8). While the reader is at the
    // newest entry, follow them there; once they have scrolled up, leave
    // `scrollTop` alone until `jumpToLatest` runs.
    const observer = new MutationObserver(() => {
      if (atBottomRef.current) {
        el.scrollTop = el.scrollHeight;
      }
    });
    observer.observe(el, { childList: true, subtree: true });

    return () => {
      el.removeEventListener("scroll", handleScroll);
      observer.disconnect();
    };
  }, []);

  return { scrollRef, atBottom, jumpToLatest };
}
