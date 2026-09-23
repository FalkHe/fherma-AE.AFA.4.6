// The pure wire -> row mapper for the play screen's transcript (sprint
// 010/06 WI1, I1). Every player-visible entry kind the backend can write
// (`backend/app/modules/playthrough/schemas.py` EVENT_PAYLOADS) becomes
// exactly one of five row shapes, or no row at all -- never a thrown error,
// since a malformed or future/unknown payload must not break the screen.
//
// No `t()` call anywhere in this file: a `system` row carries a `key` plus
// `values` only, and the component that draws it looks the wording up in
// `core/i18n/locales/en/play.json` under `system.<key>` -- the game writes
// no wording at all (sprint brief).
import type { components } from "../../api/schema";

export type EventRead = components["schemas"]["EventRead"];

/** Looked up as `system.<key>` in the `play` i18n namespace. */
export type SystemKey =
  | "ruleLookedUp"
  | "itemTaken"
  | "itemDropped"
  | "itemGiven"
  | "hpChanged"
  | "wayOpened"
  | "check";

export type TranscriptRow =
  | { kind: "narration"; id: string; text: string; at: string }
  | { kind: "player"; id: string; author: string; text: string; at: string }
  | { kind: "system"; id: string; key: SystemKey; values: Record<string, string | number> }
  | { kind: "dice"; id: string; label: string; notation: string; breakdown: string; total: number }
  | { kind: "divider"; id: string; scene: string };

type Payload = EventRead["payload"];

function str(payload: Payload, key: string): string {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

function num(payload: Payload, key: string): number {
  const value = payload[key];
  return typeof value === "number" ? value : 0;
}

function numberArray(payload: Payload, key: string): number[] {
  const value = payload[key];
  return Array.isArray(value) ? value.filter((item): item is number => typeof item === "number") : [];
}

/** `context`/`toName`-style nested field, read defensively: `roll_requested`'s
 * `context` is free-form (`schemas.py:363-375`), never guaranteed to be an
 * object at all. */
function nestedString(value: unknown, key: string): string {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    const nested = (value as Record<string, unknown>)[key];
    return typeof nested === "string" ? nested : "";
  }
  return "";
}

/** `"ability_check"` -> `"Ability check"` -- the roll kind, read as prose
 * rather than the wire's snake_case token, for the one case (AC3 fix) where
 * a check line has neither an ability nor a skill to show (attack, damage,
 * initiative and custom rolls carry neither, per `game/agent/tools.py`'s
 * `roll_dice`/`request_player_roll` docstrings -- the common case for those
 * kinds, not an edge one). */
function humanizeRollKind(kind: string): string {
  if (kind === "") {
    return "";
  }
  const spaced = kind.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** `faces` joined, the signed `modifier` appended when it is non-zero --
 * e.g. `faces: [13], modifier: 1` -> `"13 + 1"` (D12 §2's dice chip). */
function formatBreakdown(faces: number[], modifier: number): string {
  const dice = faces.join(" + ");
  if (modifier === 0) {
    return dice;
  }
  const sign = modifier > 0 ? "+" : "-";
  return dice === "" ? `${sign} ${Math.abs(modifier)}` : `${dice} ${sign} ${Math.abs(modifier)}`;
}

/** `system.check`'s `values` -- ability and skill together when both are
 * known (`context: "full"`, `play.json`'s `check_full`), the ability alone
 * when there is no skill (the base `check` key, the common shape:
 * `request_player_roll`'s own docstring gives only `{"ability": …}` for a
 * check/save), and the roll's own kind, read as prose, when neither is
 * known (`context: "kind"`, `check_kind` -- attack, damage, initiative and
 * custom rolls carry no ability at all). The difficulty is never included
 * here either way -- it lives only on the Dungeon Master's private
 * `tool_call` row (research.md, sprint 010/06) -- and is never invented.
 * `context` rides along inside `values` on purpose: `SystemLine` (WI2)
 * calls `t("system.check", values)` generically, and i18next's own context
 * selection reads that same options object -- no sentence is composed here,
 * only which of `play.json`'s own strings applies. */
function checkRow(event: EventRead): TranscriptRow {
  const payload = event.payload;
  const ability = nestedString(payload.context, "ability");
  const skill = nestedString(payload.context, "skill");
  if (ability !== "" && skill !== "") {
    return { kind: "system", id: event.id, key: "check", values: { ability, skill, context: "full" } };
  }
  if (ability !== "") {
    return { kind: "system", id: event.id, key: "check", values: { ability } };
  }
  return {
    kind: "system",
    id: event.id,
    key: "check",
    values: { kind: humanizeRollKind(str(payload, "kind")), context: "kind" },
  };
}

function itemMovedRow(event: EventRead): TranscriptRow {
  const payload = event.payload;
  const name = str(payload, "actorName");
  const item = str(payload, "itemName");
  const movement = str(payload, "movement");
  if (movement === "given") {
    return { kind: "system", id: event.id, key: "itemGiven", values: { name, item, to: str(payload, "toName") } };
  }
  if (movement === "dropped") {
    return { kind: "system", id: event.id, key: "itemDropped", values: { name, item } };
  }
  return { kind: "system", id: event.id, key: "itemTaken", values: { name, item } };
}

/** `label` favours the linked `roll_requested`'s `context.skill`, then its
 * `.ability`, and only falls back to the roll's own `kind` (e.g.
 * `"ability_check"`) when the request carried neither as a string -- or
 * when the roll names no request at all (a roll the game makes on its own,
 * D12 §1.9). */
function rollRow(event: EventRead, requests: Map<string, Payload>): TranscriptRow {
  const payload = event.payload;
  const requestId = str(payload, "requestId");
  const linked = requestId !== "" ? requests.get(requestId) : undefined;
  const skill = linked ? nestedString(linked.context, "skill") : "";
  const ability = linked ? nestedString(linked.context, "ability") : "";
  const label = skill || ability || str(payload, "kind");
  return {
    kind: "dice",
    id: event.id,
    label,
    notation: str(payload, "formula"),
    breakdown: formatBreakdown(numberArray(payload, "faces"), num(payload, "modifier")),
    total: num(payload, "total"),
  };
}

function toRow(event: EventRead, heroName: string, requests: Map<string, Payload>): TranscriptRow | null {
  const payload = event.payload;
  switch (event.type) {
    case "narration":
    case "question":
      return { kind: "narration", id: event.id, text: str(payload, "text"), at: event.createdAt };
    case "player_action":
      return { kind: "player", id: event.id, author: heroName, text: str(payload, "text"), at: event.createdAt };
    case "rule_looked_up":
      return { kind: "system", id: event.id, key: "ruleLookedUp", values: { topic: str(payload, "topic") } };
    case "item_moved":
      return itemMovedRow(event);
    case "hp_changed":
      return {
        kind: "system",
        id: event.id,
        key: "hpChanged",
        values: { name: str(payload, "targetName"), before: num(payload, "before"), after: num(payload, "after") },
      };
    case "way_opened":
      return {
        kind: "system",
        id: event.id,
        key: "wayOpened",
        values: { name: str(payload, "actorName"), action: str(payload, "action") },
      };
    case "roll_requested":
      return checkRow(event);
    case "roll":
      // The dice chip's verdict (made it / missed) is never on this row for
      // the same reason -- deliberately omitted, never invented.
      return rollRow(event, requests);
    case "scene_entered": {
      const scene = str(payload, "sceneTitle");
      return scene === "" ? null : { kind: "divider", id: event.id, scene };
    }
    default:
      // `adventure_started`/`adventure_completed`, `system`/`error`/
      // `warning`, `tool_call`, and any type this mapper does not yet know
      // about -- all silently produce no row.
      return null;
  }
}

/** Translates one run's recorded, player-visible transcript into the rows
 * D12 draws. Pure: the same `events` always yields the same rows, and
 * nothing here reaches into i18n, the network or any other side effect. */
export function toTranscriptRows(events: EventRead[], heroName: string): TranscriptRow[] {
  const requests = new Map<string, Payload>();
  for (const event of events) {
    if (event.type === "roll_requested") {
      requests.set(event.id, event.payload);
    }
  }

  const rows: TranscriptRow[] = [];
  for (const event of events) {
    const row = toRow(event, heroName, requests);
    if (row !== null) {
      rows.push(row);
    }
  }
  return rows;
}
