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

// The dashboard's own "Begin" vs "Resume" wording (sprint 007/07 WI1, AC2;
// narrowed sprint 007/08 WI1 AC3): a run still reading "New" (never
// started) offers to "Begin" it, one already under way offers to "Resume"
// it, and an archived run (status `archived` or `finished`) offers nothing
// at all — `null` tells the one caller, `CampaignCard.tsx`, to render no
// action block, since nothing can unarchive a run in this sprint's contract.
export function runActionKey(status: string): "dashboard.card.begin" | "dashboard.card.resume" | null {
  const key = runStatusKey(status);
  if (key === "run.status.archived") {
    return null;
  }
  return key === "run.status.new" ? "dashboard.card.begin" : "dashboard.card.resume";
}
