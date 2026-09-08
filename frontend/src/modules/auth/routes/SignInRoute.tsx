// ui-spec.md §3.1. Reads the guard's redirect state to decide whether the
// session-expired warning shows (§6.3 R14) and sets the per-route document
// title (§7).
import { useEffect } from "react";
import { Link as RouterLink, useLocation } from "react-router";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import { AuthCard } from "../components/AuthCard";
import { SignInForm } from "../components/SignInForm";
import type { AuthRedirectState } from "../components/RequireAuth";

export function SignInRoute() {
  const { t } = useTranslation("auth");
  const { t: tCommon } = useTranslation("common");
  const location = useLocation();
  const state = location.state as AuthRedirectState | null;
  const sessionExpired = state?.reason === "sessionExpired";

  useEffect(() => {
    document.title = `${t("signIn.title")} · ${tCommon("app.title")}`;
  }, [t, tCommon]);

  return (
    <AuthCard
      title={t("signIn.title")}
      footer={
        <Typography variant="body2">
          {t("signIn.noAccount")} <Link component={RouterLink} to="/signup">{t("signIn.createAccount")}</Link>
        </Typography>
      }
    >
      <SignInForm sessionExpired={sessionExpired} />
    </AuthCard>
  );
}
