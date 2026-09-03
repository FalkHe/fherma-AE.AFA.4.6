import Alert from "@mui/material/Alert";
import Icon from "@mui/material/Icon";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useServerEventsStatus } from "../hooks/useServerEvents";

/**
 * The "live updates are down" warning, shared by the admin chrome and the chat
 * view.
 *
 * Two screens depend on the event stream for different reasons — the admin
 * watches ingestion progress, a customer waits for the advisor's reply — so both
 * must be able to explain why nothing is moving. Everything that decision needs
 * is encapsulated here: the stream status, the grace period, and the alert
 * itself. Render it unconditionally; it returns `null` while the stream is up.
 */

/**
 * How long the event stream may be down before the user is told about it.
 *
 * The status starts out `false` (nothing is connected until the stream opens)
 * and a network blip reconnects on its own within a second or two, so warning
 * immediately would mean a banner flashing on every page load.
 */
const DISCONNECT_GRACE_MS = 5_000;

/**
 * The alert, after the grace period has passed.
 *
 * The grace timer lives in a component that is mounted only while the stream is
 * down, which is what resets it: a reconnect unmounts this and takes the elapsed
 * grace with it, so the next interruption is granted its own five seconds of
 * silence. (Resetting the state from an effect instead is the pattern eslint's
 * `react-hooks/set-state-in-effect` rightly forbids.)
 */
function DisconnectNotice() {
  const { t } = useTranslation();
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setIsVisible(true), DISCONNECT_GRACE_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, []);

  if (!isVisible) {
    return null;
  }

  return (
    <Alert severity="warning" icon={<Icon>sync_problem</Icon>} sx={{ mb: 2 }}>
      {t("common.live.disconnected")}
    </Alert>
  );
}

export function LiveConnectionAlert() {
  const { connected } = useServerEventsStatus();

  return connected ? null : <DisconnectNotice />;
}
