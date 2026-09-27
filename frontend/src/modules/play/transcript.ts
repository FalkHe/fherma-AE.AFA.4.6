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
  | {
      kind: "dice";
      id: string;
      label: string;
      notation: string;
      breakdown: string;
      total: number;
      verdict?: "madeIt" | "missed";
    }
  | { kind: "divider"; id: string; scene: string }
  | { kind: "ending"; id: string; outcome: RunOutcome };

/** `finish_run`'s own `Literal` (`backend/app/modules/playthrough/service.py`)
 * -- the only three values a `system` event's `details.outcome` ever
 * carries. */
export type RunOutcome = "victory" | "defeat" | "authored";

const RUN_OUTCOMES: readonly RunOutcome[] = ["victory", "defeat", "authored"];

/** The single question or dice roll the game is waiting on (sprint 010/09
 * WI2, I1) -- the events read's `awaiting` marker, resolved against the
 * `events` it came with into what D12's choice/roll buttons need: a
 * `question` event's `options` verbatim, or a `roll_requested` event's
 * `formula` as `notation`. */
export type PendingPrompt =
  | { kind: "choice"; id: string; options: string[] }
  | { kind: "roll"; id: string; notation: string };

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

function stringArray(payload: Payload, key: string): string[] {
  const value = payload[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
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

/** Same defensive read as `nestedString`, for `context.dc` (sprint 010/09
 * WI2, I1) -- undefined, never 0, when it is absent or not a number, so a
 * missing difficulty is never mistaken for DC 0. */
function nestedNumber(value: unknown, key: string): number | undefined {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    const nested = (value as Record<string, unknown>)[key];
    return typeof nested === "number" ? nested : undefined;
  }
  return undefined;
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
 * custom rolls carry no ability at all). `context` rides along inside
 * `values` on purpose: `SystemLine` (WI2) calls `t("system.check", values)`
 * generically, and i18next's own context selection reads that same options
 * object -- no sentence is composed here, only which of `play.json`'s own
 * strings applies.
 *
 * A numeric `context.dc` (sprint 010/09 WI2, I1 -- the transcript read's
 * `roll_requested` payloads may now carry one) switches to the sibling
 * `_dc` context variant (`check_full_dc` / `check_dc` / `check_kind_dc`)
 * and adds `dc` to `values`, so the difficulty shows on the check line
 * itself once the game states one; still never invented when absent. */
function checkRow(event: EventRead): TranscriptRow {
  const payload = event.payload;
  const ability = nestedString(payload.context, "ability");
  const skill = nestedString(payload.context, "skill");
  const dc = nestedNumber(payload.context, "dc");
  if (ability !== "" && skill !== "") {
    const values: Record<string, string | number> = { ability, skill, context: dc === undefined ? "full" : "full_dc" };
    if (dc !== undefined) {
      values.dc = dc;
    }
    return { kind: "system", id: event.id, key: "check", values };
  }
  if (ability !== "") {
    const values: Record<string, string | number> = dc === undefined ? { ability } : { ability, dc, context: "dc" };
    return { kind: "system", id: event.id, key: "check", values };
  }
  const kind = humanizeRollKind(str(payload, "kind"));
  const values: Record<string, string | number> =
    dc === undefined ? { kind, context: "kind" } : { kind, dc, context: "kind_dc" };
  return { kind: "system", id: event.id, key: "check", values };
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
 * D12 §1.9).
 *
 * `verdict` (sprint 010/09 WI2, I1) is `"madeIt"` when the roll's `total`
 * meets or beats the linked request's `context.dc`, `"missed"` when it
 * falls short, and left off the row entirely -- not guessed at -- when the
 * request carries no numeric DC or the roll names no request at all. */
function rollRow(event: EventRead, requests: Map<string, Payload>): TranscriptRow {
  const payload = event.payload;
  const requestId = str(payload, "requestId");
  const linked = requestId !== "" ? requests.get(requestId) : undefined;
  const skill = linked ? nestedString(linked.context, "skill") : "";
  const ability = linked ? nestedString(linked.context, "ability") : "";
  const label = skill || ability || str(payload, "kind");
  const dc = linked ? nestedNumber(linked.context, "dc") : undefined;
  const total = num(payload, "total");
  const row: TranscriptRow = {
    kind: "dice",
    id: event.id,
    label,
    notation: str(payload, "formula"),
    breakdown: formatBreakdown(numberArray(payload, "faces"), num(payload, "modifier")),
    total,
  };
  return dc === undefined ? row : { ...row, verdict: total >= dc ? "madeIt" : "missed" };
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
      return rollRow(event, requests);
    case "scene_entered": {
      const scene = str(payload, "sceneTitle");
      return scene === "" ? null : { kind: "divider", id: event.id, scene };
    }
    case "system": {
      // `finish_run` is the only writer of a `system` event (`service.py`)
      // and always carries `details.outcome`; a refusal event or any other
      // future `system` shape carries no such field and silently produces
      // no row, same as the default branch below.
      const outcome = nestedString(payload.details, "outcome");
      return RUN_OUTCOMES.includes(outcome as RunOutcome)
        ? { kind: "ending", id: event.id, outcome: outcome as RunOutcome }
        : null;
    }
    default:
      // `adventure_started`/`adventure_completed`, `error`/`warning`,
      // `tool_call`, and any type this mapper does not yet know about --
      // all silently produce no row.
      return null;
  }
}

/** Whether a turn is still running (sprint 010/07 WI5, I5). The game writes
 * a `player_action` event as a turn's first entry and a `narration` event
 * as its last, immediately before the turn ends -- everything else is
 * mid-turn -- so a non-empty transcript whose last event is not a
 * narration means the turn has not closed yet. An empty transcript (e.g.
 * right after a reload, before the first read lands) is never unfinished. */
export function isTurnUnfinished(events: EventRead[]): boolean {
  return events.length > 0 && events[events.length - 1].type !== "narration";
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

/** Resolves the events read's `awaiting` marker (`"none"`,
 * `"answer:<eventId>"` or `"roll:<eventId>"`) against the same `events`
 * into the one prompt D12's choice/roll buttons act on (sprint 010/09 WI2,
 * I1). `null` covers every case that is not a clean, matching prompt --
 * `"none"`, an id `events` does not carry, the marker's prefix pointing at
 * the wrong event type, and a `question` whose `options` is empty or
 * missing -- so a malformed or stale marker never renders a broken button,
 * mirroring `toTranscriptRows`'s own never-throw stance. */
export function toPendingPrompt(events: EventRead[], awaiting: string): PendingPrompt | null {
  const separatorIndex = awaiting.indexOf(":");
  if (separatorIndex === -1) {
    return null;
  }
  const prefix = awaiting.slice(0, separatorIndex);
  const id = awaiting.slice(separatorIndex + 1);
  const target = events.find((candidate) => candidate.id === id);
  if (target === undefined) {
    return null;
  }
  if (prefix === "answer" && target.type === "question") {
    const options = stringArray(target.payload, "options");
    return options.length === 0 ? null : { kind: "choice", id, options };
  }
  if (prefix === "roll" && target.type === "roll_requested") {
    return { kind: "roll", id, notation: str(target.payload, "formula") };
  }
  return null;
}
