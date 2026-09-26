// Sprint 010/06 WI1, I1. Behaviours: each recorded kind becomes the row D12
// draws, or no row at all; a scene entry becomes a divider only when it
// names the scene; an unknown or Dungeon-Master-only kind produces nothing
// and never throws; the mapper is pure.
import { describe, expect, it } from "vitest";

import i18n from "../../core/i18n";
import { isTurnUnfinished, toPendingPrompt, toTranscriptRows, type EventRead, type SystemKey } from "./transcript";

// `SystemLine` (WI2) calls `t(\`system.${key}\`, values)` verbatim -- this
// reproduces exactly that call, so a `check` row's `values` (in particular
// its `context`) is checked against what it actually renders as, not just
// against the row's own shape (AC3 fix: a missing skill or ability must
// never render as stray empty brackets).
function renderSystemRow(key: SystemKey, values: Record<string, string | number>): string {
  return i18n.t(`play:system.${key}`, values);
}

let counter = 0;

function event(type: string, payload: Record<string, unknown>, overrides: Partial<EventRead> = {}): EventRead {
  counter += 1;
  return {
    id: `evt-${counter}`,
    type,
    turnId: "turn-1",
    payload,
    createdAt: "2026-09-08T12:34:56.789012+00:00",
    ...overrides,
  };
}

describe("toTranscriptRows (I1)", () => {
  it("maps a narration event to a narration row", () => {
    const e = event("narration", { text: "Greenhollow is a dozen houses round a well." }, { id: "n1", createdAt: "2026-09-08T21:02:00+00:00" });

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([
      { kind: "narration", id: "n1", text: "Greenhollow is a dozen houses round a well.", at: "2026-09-08T21:02:00+00:00" },
    ]);
  });

  it("maps a question event to a narration row, dropping its options", () => {
    const e = event(
      "question",
      { text: "Take it?", options: ["Take the knife", "Leave it with Mira"] },
      { id: "q1", createdAt: "2026-09-08T21:07:00+00:00" },
    );

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([
      { kind: "narration", id: "q1", text: "Take it?", at: "2026-09-08T21:07:00+00:00" },
    ]);
  });

  it("maps a player_action event to a player row, authored by the passed-in hero name", () => {
    const e = event(
      "player_action",
      { text: "I pick up the horseshoe and ask Mira who found it." },
      { id: "p1", createdAt: "2026-09-08T21:04:00+00:00" },
    );

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([
      {
        kind: "player",
        id: "p1",
        author: "Rosalind Thorn",
        text: "I pick up the horseshoe and ask Mira who found it.",
        at: "2026-09-08T21:04:00+00:00",
      },
    ]);
  });

  it("maps rule_looked_up to a system row keyed ruleLookedUp", () => {
    const e = event("rule_looked_up", { topic: "Chapter 7 › Using Ability Scores › Hiding" }, { id: "r1" });

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([
      { kind: "system", id: "r1", key: "ruleLookedUp", values: { topic: "Chapter 7 › Using Ability Scores › Hiding" } },
    ]);
  });

  it.each([
    ["taken", "itemTaken", { name: "Rosalind Thorn", item: "Bent Horseshoe" }],
    ["dropped", "itemDropped", { name: "Rosalind Thorn", item: "Bent Horseshoe" }],
  ] as const)("maps item_moved (movement=%s) to a system row keyed %s", (movement, key, values) => {
    const e = event(
      "item_moved",
      { movement, actorId: "hero-1", actorName: "Rosalind Thorn", itemId: "item-1", itemName: "Bent Horseshoe" },
      { id: "i1" },
    );

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([{ kind: "system", id: "i1", key, values }]);
  });

  it("maps item_moved (movement=given) to a system row keyed itemGiven, carrying the receiver", () => {
    const e = event(
      "item_moved",
      {
        movement: "given",
        actorId: "hero-1",
        actorName: "Rosalind Thorn",
        itemId: "item-1",
        itemName: "Bent Horseshoe",
        toId: "hero-2",
        toName: "Mira",
      },
      { id: "i2" },
    );

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([
      { kind: "system", id: "i2", key: "itemGiven", values: { name: "Rosalind Thorn", item: "Bent Horseshoe", to: "Mira" } },
    ]);
  });

  it("maps hp_changed to a system row keyed hpChanged, carrying only before/after", () => {
    const e = event(
      "hp_changed",
      { targetId: "hero-1", targetName: "Rosalind Thorn", before: 12, after: 9, maxHp: 12, alive: true, down: false },
      { id: "h1" },
    );

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([
      { kind: "system", id: "h1", key: "hpChanged", values: { name: "Rosalind Thorn", before: 12, after: 9 } },
    ]);
  });

  it("maps way_opened to a system row keyed wayOpened", () => {
    const e = event(
      "way_opened",
      { actorId: "hero-1", actorName: "Rosalind Thorn", objectId: "obj-1", objectName: "thornbrush", action: "cut the thornbrush open" },
      { id: "w1" },
    );

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([
      { kind: "system", id: "w1", key: "wayOpened", values: { name: "Rosalind Thorn", action: "cut the thornbrush open" } },
    ]);
  });

  it("maps roll_requested (ability and skill both known) to a system check row, without a difficulty", () => {
    const e = event(
      "roll_requested",
      { kind: "ability_check", actorId: "hero-1", formula: "1d20+1", context: { ability: "Intelligence", skill: "Investigation" } },
      { id: "req1" },
    );

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([
      { kind: "system", id: "req1", key: "check", values: { ability: "Intelligence", skill: "Investigation", context: "full" } },
    ]);
    expect(renderSystemRow("check", { ability: "Intelligence", skill: "Investigation", context: "full" })).toBe(
      "Intelligence (Investigation)",
    );
  });

  it("maps roll_requested (ability known, no skill -- a saving throw) to the ability alone, not empty brackets", () => {
    const e = event(
      "roll_requested",
      { kind: "saving_throw", actorId: "hero-1", formula: "1d20+2", context: { ability: "Dexterity" } },
      { id: "req1b" },
    );

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([
      { kind: "system", id: "req1b", key: "check", values: { ability: "Dexterity" } },
    ]);
    expect(renderSystemRow("check", { ability: "Dexterity" })).toBe("Dexterity");
  });

  it("maps roll_requested (neither ability nor skill known -- an initiative roll) to the roll's own kind, not empty brackets", () => {
    const e = event("roll_requested", { kind: "initiative", actorId: "hero-1", formula: "1d20", context: null }, { id: "req2" });

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([
      { kind: "system", id: "req2", key: "check", values: { kind: "Initiative", context: "kind" } },
    ]);
    expect(renderSystemRow("check", { kind: "Initiative", context: "kind" })).toBe("Initiative");
  });

  it("maps roll_requested carrying a numeric context.dc to a check row with the DC context variant (← I1)", () => {
    const e = event(
      "roll_requested",
      { kind: "ability_check", actorId: "hero-1", formula: "1d20+1", context: { ability: "Intelligence", skill: "Investigation", dc: 15 } },
      { id: "req5" },
    );

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([
      { kind: "system", id: "req5", key: "check", values: { ability: "Intelligence", skill: "Investigation", dc: 15, context: "full_dc" } },
    ]);
    expect(
      renderSystemRow("check", { ability: "Intelligence", skill: "Investigation", dc: 15, context: "full_dc" }),
    ).toBe("Intelligence (Investigation) · DC 15");
  });

  it("maps roll_requested (ability only, with a DC) to the ability-plus-DC context variant (← I1)", () => {
    const e = event("roll_requested", { kind: "saving_throw", actorId: "hero-1", formula: "1d20+2", context: { ability: "Dexterity", dc: 12 } }, { id: "req6" });

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([
      { kind: "system", id: "req6", key: "check", values: { ability: "Dexterity", dc: 12, context: "dc" } },
    ]);
    expect(renderSystemRow("check", { ability: "Dexterity", dc: 12, context: "dc" })).toBe("Dexterity · DC 12");
  });

  it("maps roll_requested (neither ability nor skill, with a DC) to the kind-plus-DC context variant (← I1)", () => {
    const e = event("roll_requested", { kind: "initiative", actorId: "hero-1", formula: "1d20", context: { dc: 10 } }, { id: "req7" });

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([
      { kind: "system", id: "req7", key: "check", values: { kind: "Initiative", dc: 10, context: "kind_dc" } },
    ]);
    expect(renderSystemRow("check", { kind: "Initiative", dc: 10, context: "kind_dc" })).toBe("Initiative · DC 10");
  });

  it("maps a linked roll to a dice row, breakdown joining faces and the signed modifier, label from context.skill", () => {
    const request = event(
      "roll_requested",
      { kind: "ability_check", actorId: "hero-1", formula: "1d20+1", context: { ability: "Intelligence", skill: "Investigation" } },
      { id: "req3" },
    );
    const roll = event(
      "roll",
      { requestId: "req3", kind: "ability_check", actorId: "hero-1", formula: "1d20+1", faces: [13], modifier: 1, total: 14 },
      { id: "roll3" },
    );

    const rows = toTranscriptRows([request, roll], "Rosalind Thorn");

    expect(rows).toContainEqual({
      kind: "dice",
      id: "roll3",
      label: "Investigation",
      notation: "1d20+1",
      breakdown: "13 + 1",
      total: 14,
    });
  });

  it("gives a linked roll a madeIt verdict when its total meets the request's DC (← I1)", () => {
    const request = event(
      "roll_requested",
      { kind: "ability_check", actorId: "hero-1", formula: "1d20+1", context: { ability: "Intelligence", skill: "Investigation", dc: 14 } },
      { id: "req8" },
    );
    const roll = event(
      "roll",
      { requestId: "req8", kind: "ability_check", actorId: "hero-1", formula: "1d20+1", faces: [13], modifier: 1, total: 14 },
      { id: "roll8" },
    );

    expect(toTranscriptRows([request, roll], "Rosalind Thorn")).toContainEqual(
      expect.objectContaining({ kind: "dice", id: "roll8", total: 14, verdict: "madeIt" }),
    );
  });

  it("gives a linked roll a missed verdict when its total falls short of the request's DC (← I1)", () => {
    const request = event(
      "roll_requested",
      { kind: "ability_check", actorId: "hero-1", formula: "1d20+1", context: { ability: "Intelligence", skill: "Investigation", dc: 20 } },
      { id: "req9" },
    );
    const roll = event(
      "roll",
      { requestId: "req9", kind: "ability_check", actorId: "hero-1", formula: "1d20+1", faces: [13], modifier: 1, total: 14 },
      { id: "roll9" },
    );

    expect(toTranscriptRows([request, roll], "Rosalind Thorn")).toContainEqual(
      expect.objectContaining({ kind: "dice", id: "roll9", total: 14, verdict: "missed" }),
    );
  });

  it("leaves verdict absent when the linked request carries no DC (← I1)", () => {
    const request = event(
      "roll_requested",
      { kind: "ability_check", actorId: "hero-1", formula: "1d20+1", context: { ability: "Intelligence", skill: "Investigation" } },
      { id: "req10" },
    );
    const roll = event(
      "roll",
      { requestId: "req10", kind: "ability_check", actorId: "hero-1", formula: "1d20+1", faces: [13], modifier: 1, total: 14 },
      { id: "roll10" },
    );

    const row = toTranscriptRows([request, roll], "Rosalind Thorn").find((r) => r.kind === "dice");
    expect(row).not.toHaveProperty("verdict");
  });

  it("falls back to the linked request's ability when it names no skill", () => {
    const request = event(
      "roll_requested",
      { kind: "saving_throw", actorId: "hero-1", formula: "1d20+2", context: { ability: "Dexterity" } },
      { id: "req4" },
    );
    const roll = event(
      "roll",
      { requestId: "req4", kind: "saving_throw", actorId: "hero-1", formula: "1d20+2", faces: [9], modifier: 2, total: 11 },
      { id: "roll4" },
    );

    const rows = toTranscriptRows([request, roll], "Rosalind Thorn");

    expect(rows.find((row) => row.kind === "dice")).toMatchObject({ label: "Dexterity" });
  });

  it("falls back to the roll's own kind when it names no request at all (an unprompted roll)", () => {
    const roll = event(
      "roll",
      { requestId: null, kind: "initiative", actorId: "hero-1", formula: "1d20", faces: [15], modifier: 0, total: 15 },
      { id: "roll5" },
    );

    expect(toTranscriptRows([roll], "Rosalind Thorn")).toEqual([
      { kind: "dice", id: "roll5", label: "initiative", notation: "1d20", breakdown: "15", total: 15 },
    ]);
  });

  it("becomes a divider only when scene_entered carries a sceneTitle", () => {
    const named = event(
      "scene_entered",
      { adventureRunId: "ar-1", sceneId: "scene-1", sceneTitle: "The Village Green" },
      { id: "s1" },
    );
    const unnamed = event("scene_entered", { adventureRunId: "ar-1", sceneId: "scene-2", sceneTitle: null }, { id: "s2" });
    const missing = event("scene_entered", { adventureRunId: "ar-1", sceneId: "scene-3" }, { id: "s3" });

    expect(toTranscriptRows([named], "Rosalind Thorn")).toEqual([{ kind: "divider", id: "s1", scene: "The Village Green" }]);
    expect(toTranscriptRows([unnamed], "Rosalind Thorn")).toEqual([]);
    expect(toTranscriptRows([missing], "Rosalind Thorn")).toEqual([]);
  });

  it.each(["tool_call", "adventure_started", "adventure_completed", "system", "error", "warning", "something_unknown"])(
    "produces no row for a Dungeon-Master-only or unknown type (%s), and does not throw",
    (type) => {
      const e = event(type, { anything: "goes", nested: { also: true } }, { id: "x1" });

      expect(() => toTranscriptRows([e], "Rosalind Thorn")).not.toThrow();
      expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([]);
    },
  );

  it.each(["victory", "defeat", "authored"] as const)(
    "maps a system event whose details name outcome %s to an ending row",
    (outcome) => {
      const e = event(
        "system",
        { message: "The party has fallen. The adventure ends in defeat.", details: { outcome } },
        { id: "end1" },
      );

      expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([{ kind: "ending", id: "end1", outcome }]);
    },
  );

  it("produces no row for a system event whose details name no recognised outcome", () => {
    const e = event("system", { message: "campaign run is already finished", details: { reason: "x" } }, { id: "s9" });

    expect(toTranscriptRows([e], "Rosalind Thorn")).toEqual([]);
  });

  it("is pure: the same events and hero name always yield an equal result", () => {
    const events = [
      event("narration", { text: "Once upon a time." }, { id: "a1" }),
      event("player_action", { text: "I look around." }, { id: "a2" }),
      event("scene_entered", { adventureRunId: "ar-1", sceneId: "scene-1", sceneTitle: "The Village Green" }, { id: "a3" }),
    ];

    const first = toTranscriptRows(events, "Rosalind Thorn");
    const second = toTranscriptRows(events, "Rosalind Thorn");

    expect(first).toEqual(second);
  });

  it("keeps rows in the recorded events' order", () => {
    const events = [
      event("narration", { text: "First." }, { id: "o1" }),
      event("player_action", { text: "Second." }, { id: "o2" }),
      event("narration", { text: "Third." }, { id: "o3" }),
    ];

    const rows = toTranscriptRows(events, "Rosalind Thorn");

    expect(rows.map((row) => row.id)).toEqual(["o1", "o2", "o3"]);
  });
});

// Sprint 010/07 WI5, I5. A turn is still running whenever the transcript is
// non-empty and its last recorded event is not the closing narration.
describe("isTurnUnfinished (I5)", () => {
  it("is false for an empty transcript (AC4: after a reload with nothing recorded)", () => {
    expect(isTurnUnfinished([])).toBe(false);
  });

  it("is false when the last event is a narration (turn closed)", () => {
    const events = [
      event("player_action", { text: "I look around." }, { id: "p1" }),
      event("narration", { text: "The room is empty." }, { id: "n1" }),
    ];

    expect(isTurnUnfinished(events)).toBe(false);
  });

  it("is true when the last event is a roll (turn still running)", () => {
    const events = [
      event("player_action", { text: "I attack." }, { id: "p1" }),
      event("roll", { kind: "attack", formula: "1d20", faces: [14], modifier: 2, total: 16 }, { id: "r1" }),
    ];

    expect(isTurnUnfinished(events)).toBe(true);
  });
});

// Sprint 010/09 WI2, I1. Turns the events read's `awaiting` marker into the
// single prompt D12's choice/roll buttons render, or null when there is
// nothing to answer yet or the marker cannot be resolved against `events`.
describe("toPendingPrompt (I1)", () => {
  it("resolves a pending question to a choice prompt, options verbatim", () => {
    const q = event("question", { text: "Take it?", options: ["Take the knife", "Leave it with Mira"] }, { id: "q1" });

    expect(toPendingPrompt([q], "answer:q1")).toEqual({
      kind: "choice",
      id: "q1",
      options: ["Take the knife", "Leave it with Mira"],
    });
  });

  it("resolves a pending roll_requested to a roll prompt, notation from formula", () => {
    const r = event("roll_requested", { kind: "ability_check", formula: "1d20+3", context: { ability: "Strength" } }, { id: "req1" });

    expect(toPendingPrompt([r], "roll:req1")).toEqual({ kind: "roll", id: "req1", notation: "1d20+3" });
  });

  it("is null for awaiting=none", () => {
    const q = event("question", { text: "Take it?", options: ["Yes", "No"] }, { id: "q1" });

    expect(toPendingPrompt([q], "none")).toBeNull();
  });

  it("is null when the awaited id names no recorded event", () => {
    expect(toPendingPrompt([], "answer:missing")).toBeNull();
  });

  it("is null when the awaited id names an event of the wrong type", () => {
    const r = event("roll_requested", { kind: "ability_check", formula: "1d20", context: {} }, { id: "req1" });

    expect(toPendingPrompt([r], "answer:req1")).toBeNull();
  });

  it("is null when a question's options are empty or missing", () => {
    const empty = event("question", { text: "Take it?", options: [] }, { id: "q1" });
    const missing = event("question", { text: "Take it?" }, { id: "q2" });

    expect(toPendingPrompt([empty], "answer:q1")).toBeNull();
    expect(toPendingPrompt([missing], "answer:q2")).toBeNull();
  });
});
