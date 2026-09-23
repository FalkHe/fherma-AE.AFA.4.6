// The opening turn's one-shot trigger (sprint 010/08 WI2, I3 ← AC4). Router
// state survives a reload (it lives in the history entry, not memory), so a
// flag read straight off `useLocation().state` would fire `onStart` again on
// every remount of this hook after a refresh -- the guard here is twofold:
// the flag is cleared from history the moment it is seen (`navigate(...,
// { replace: true, state: null })`, same pattern as `useSignOut.ts`'s own
// post-sign-out replace), and `firedRef` stops a second call within the same
// mount (React's dev-mode double-invoke of effects, or any re-render before
// the replace's own re-render lands).
//
// `onStart` is kept in a ref rather than listed as an effect dependency --
// this hook's only contract is "fire once when the flag is set", and a
// caller that passes a fresh closure every render (the common case for an
// inline `() => startOpening()`) must never retrigger the effect on that
// account alone.
import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";

/** The router state shape this hook reads. `PlayRoute`'s own navigation
 * into `/runs/:runId/play` (WI4) sets this to mark a freshly started run. */
export interface OpeningTurnState {
  startOpening?: boolean;
}

export function useOpeningTurn(onStart: () => void): void {
  const location = useLocation();
  const navigate = useNavigate();
  const onStartRef = useRef(onStart);
  const firedRef = useRef(false);

  useEffect(() => {
    onStartRef.current = onStart;
  });

  useEffect(() => {
    const state = location.state as OpeningTurnState | null;
    if (firedRef.current || state?.startOpening !== true) {
      return;
    }
    firedRef.current = true;
    navigate(location.pathname, { replace: true, state: null });
    onStartRef.current();
    // Only the flag itself should ever retrigger this effect -- `onStart`
    // is read through the ref above, `navigate`/`location.pathname` are
    // read once at fire time, not re-run on their own account.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);
}
