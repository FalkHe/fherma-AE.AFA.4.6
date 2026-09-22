// ui-spec.md §3.3. Owns the single `useSignOut()` instance and renders both
// of its consumers: the button (via AppShell's `action` slot) and the error
// alert (into `children`), so both come from one mutation (step-0.1.md
// §6.3.1, UI-27).
import { useEffect, useRef } from "react";
import Alert from "@mui/material/Alert";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import { useCurrentUser } from "../../auth/hooks/useCurrentUser";
import { useSignOut } from "../../auth/hooks/useSignOut";
import { SignOutButton } from "../../auth/components/SignOutButton";
import { AppShell } from "../components/AppShell";

export function HomeRoute() {
  const { t } = useTranslation("home");
  const { t: tAuth } = useTranslation("auth");
  const { t: tCommon } = useTranslation("common");
  const { user } = useCurrentUser();
  const signOut = useSignOut();
  const greetingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    document.title = tCommon("app.title");
  }, [tCommon]);

  // The greeting is the page's <h1> and the post-navigation focus target
  // (ui-spec.md §6.5): focus it once, on arrival.
  useEffect(() => {
    greetingRef.current?.focus();
  }, []);

  return (
    <AppShell
      title={tCommon("app.title")}
      action={<SignOutButton onClick={() => signOut.mutate()} loading={signOut.isPending} />}
    >
      {signOut.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {tAuth("signOut.error")}
        </Alert>
      )}
      <Typography variant="h2" component="h1" tabIndex={-1} ref={greetingRef}>
        {t("greeting", { username: user?.username ?? "" })}
      </Typography>
    </AppShell>
  );
}
