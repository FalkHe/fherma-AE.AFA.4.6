// ui-spec.md §3.3. Sign-out now lives entirely in AccountMenu (AC3,
// modules/auth/components/AccountMenu.tsx) — this route only reads the
// current user for the greeting.
import { useEffect, useRef } from "react";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import { useCurrentUser } from "../../auth/hooks/useCurrentUser";

export function HomeRoute() {
  const { t } = useTranslation("home");
  const { t: tCommon } = useTranslation("common");
  const { user } = useCurrentUser();
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
    <Typography variant="h2" component="h1" tabIndex={-1} ref={greetingRef}>
      {t("greeting", { username: user?.username ?? "" })}
    </Typography>
  );
}
