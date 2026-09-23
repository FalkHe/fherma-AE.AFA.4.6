// Sprint 010/06 WI2. Behaviours: narration, player, system and dice rows
// each render as D12 draws them; a system line is worded from its values by
// the interface's own string, for each of the seven `SystemKey`s; a scene
// divider renders with the scene's name; an empty transcript shows D12's
// empty line; the "Jump to the latest" pill mounts only while not at the
// newest entry.
//
// `useStickToLatest`/`JumpToLatestPill` are a sibling work item's files
// (WI3, landing on this branch in parallel) -- mocked here against their
// agreed signature (`plan.md` I2) so this component's own behaviour is
// exercised independently of their real scrolling implementation.
//
// `ThinkingLine` (WI3's I3, same sibling work item) is mocked the same way,
// against its agreed contract (named export, no props, root
// `data-testid="thinking-line"`) so Transcript's own placement of it --
// last child, after the rows or the empty line -- is exercised
// independently of its real rendering.
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "../../../test/render";
import { Transcript } from "./Transcript";
import type { SystemKey, TranscriptRow } from "../transcript";
import play from "../../../core/i18n/locales/en/play.json";

const jumpToLatest = vi.fn();
let atBottom = true;

vi.mock("../hooks/useStickToLatest", () => ({
  useStickToLatest: () => ({ scrollRef: { current: null }, atBottom, jumpToLatest }),
}));

vi.mock("./JumpToLatestPill", () => ({
  JumpToLatestPill: ({ onClick }: { onClick: () => void }) => (
    <button type="button" onClick={onClick}>
      {play.jumpToLatest}
    </button>
  ),
}));

vi.mock("./ThinkingLine", () => ({
  ThinkingLine: () => <div data-testid="thinking-line">thinking</div>,
}));

describe("Transcript (WI2)", () => {
  it("renders a narration row with the Dungeon Master's name, the time and the text", () => {
    const rows: TranscriptRow[] = [
      { kind: "narration", id: "n1", text: "Greenhollow is a dozen houses round a well.", at: "2026-09-08T21:02:00Z" },
    ];

    renderWithProviders(<Transcript rows={rows} />);

    expect(screen.getByText(play.narration.author)).toBeInTheDocument();
    expect(screen.getByText("Greenhollow is a dozen houses round a well.")).toBeInTheDocument();
    expect(screen.getByText("21:02")).toBeInTheDocument();
  });

  it("renders a player row under the character's own name", () => {
    const rows: TranscriptRow[] = [
      {
        kind: "player",
        id: "p1",
        author: "Rosalind Thorn",
        text: "I pick up the horseshoe and ask Mira who found it.",
        at: "2026-09-08T21:04:00Z",
      },
    ];

    renderWithProviders(<Transcript rows={rows} />);

    expect(screen.getByText("Rosalind Thorn")).toBeInTheDocument();
    expect(screen.getByText("I pick up the horseshoe and ask Mira who found it.")).toBeInTheDocument();
  });

  it("renders a dice chip with the label, notation, breakdown and total, and no verdict", () => {
    const rows: TranscriptRow[] = [
      { kind: "dice", id: "d1", label: "Investigation", notation: "1d20+1", breakdown: "13 + 1", total: 14 },
    ];

    renderWithProviders(<Transcript rows={rows} />);

    expect(screen.getByText("Investigation")).toBeInTheDocument();
    expect(screen.getByText("1d20+1")).toBeInTheDocument();
    expect(screen.getByText("13 + 1")).toBeInTheDocument();
    expect(screen.getByText("14")).toBeInTheDocument();
    expect(screen.queryByText(/✓|✗/)).not.toBeInTheDocument();
  });

  it("renders a scene divider with the scene's name", () => {
    const rows: TranscriptRow[] = [{ kind: "divider", id: "sc1", scene: "The Village Green" }];

    renderWithProviders(<Transcript rows={rows} />);

    expect(screen.getByText("The Village Green")).toBeInTheDocument();
  });

  it("shows D12's empty line when the transcript has no rows", () => {
    renderWithProviders(<Transcript rows={[]} />);

    expect(screen.getByText(play.empty)).toBeInTheDocument();
  });

  const systemCases: Array<{ key: SystemKey; values: Record<string, string | number>; expected: string }> = [
    { key: "ruleLookedUp", values: { topic: "Investigation" }, expected: "· Checked the rules · Investigation ·" },
    { key: "itemTaken", values: { name: "Rosalind Thorn", item: "Bent Horseshoe" }, expected: "· Rosalind Thorn takes the Bent Horseshoe ·" },
    { key: "itemDropped", values: { name: "Rosalind Thorn", item: "Bent Horseshoe" }, expected: "· Rosalind Thorn drops the Bent Horseshoe ·" },
    {
      key: "itemGiven",
      values: { name: "Rosalind Thorn", item: "Bent Horseshoe", to: "Mira" },
      expected: "· Rosalind Thorn gives the Bent Horseshoe to Mira ·",
    },
    { key: "hpChanged", values: { name: "Rosalind Thorn", before: 12, after: 9 }, expected: "· Rosalind Thorn: 12 → 9 hit points ·" },
    { key: "wayOpened", values: { name: "Rosalind Thorn", action: "cuts open the thornbrush" }, expected: "· Rosalind Thorn · cuts open the thornbrush ·" },
    // `context: "full"` is `transcript.ts`'s own value for "both known" (AC3
    // fix) -- `SystemLine`'s generic `t(key, values)` call reads it as
    // i18next's context option and picks `check_full` over the bare `check`.
    {
      key: "check",
      values: { ability: "Intelligence", skill: "Investigation", context: "full" },
      expected: "· Intelligence (Investigation) ·",
    },
  ];

  it.each(systemCases)("words the '$key' system line from its values by the interface's own string", ({ key, values, expected }) => {
    const rows: TranscriptRow[] = [{ kind: "system", id: `s-${key}`, key, values }];

    renderWithProviders(<Transcript rows={rows} />);

    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("mounts the 'Jump to the latest' pill only when not at the newest entry", () => {
    atBottom = false;
    renderWithProviders(<Transcript rows={[]} />);

    expect(screen.getByRole("button", { name: play.jumpToLatest })).toBeInTheDocument();
  });

  it("does not mount the pill while already at the newest entry", () => {
    atBottom = true;
    renderWithProviders(<Transcript rows={[]} />);

    expect(screen.queryByRole("button", { name: play.jumpToLatest })).not.toBeInTheDocument();
  });

  it("renders the thinking line after the rows when a turn is running (AC2, AC4)", () => {
    const rows: TranscriptRow[] = [
      { kind: "dice", id: "d1", label: "Investigation", notation: "1d20+1", breakdown: "13 + 1", total: 14 },
    ];

    renderWithProviders(<Transcript rows={rows} thinking />);

    const log = screen.getByRole("log");
    const thinkingLine = screen.getByTestId("thinking-line");
    expect(thinkingLine).toBeInTheDocument();
    expect(log.lastElementChild).toBe(thinkingLine);
  });

  it("does not render the thinking line when no turn is running", () => {
    const rows: TranscriptRow[] = [
      { kind: "dice", id: "d1", label: "Investigation", notation: "1d20+1", breakdown: "13 + 1", total: 14 },
    ];

    renderWithProviders(<Transcript rows={rows} />);

    expect(screen.queryByTestId("thinking-line")).not.toBeInTheDocument();
  });
});
