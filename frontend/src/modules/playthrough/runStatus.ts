// A run's status vocabulary, shared by the run screen (sprint 007/05 WI1)
// and the dashboard (sprint 007/07 WI1) so both read a run's state the same
// way. `status` comes off the wire as a plain `string` (schema.d.ts), not a
// literal union, so an unrecognised value falls back to "New" rather than
// rendering nothing — extracted from `RunRoute.tsx` unchanged.
export type RunStatusKey = "run.status.new" | "run.status.inProgress" | "run.status.archived";

export function runStatusKey(status: string): RunStatusKey {
  switch (status) {
    case "ready":
    case "active":
      return "run.status.inProgress";
    case "archived":
    case "finished":
      return "run.status.archived";
    default:
      return "run.status.new";
  }
}

// The dashboard's own "Begin" vs "Resume" wording (sprint 007/07 WI1, AC2):
// only a run still reading "New" (i.e. never started) offers to "Begin" it;
// anything already under way, archived or finished opens to "Resume" —
// there is no separate "Unarchive" affordance in this sprint's contract.
export function runActionKey(status: string): "dashboard.card.begin" | "dashboard.card.resume" {
  return runStatusKey(status) === "run.status.new" ? "dashboard.card.begin" : "dashboard.card.resume";
}
