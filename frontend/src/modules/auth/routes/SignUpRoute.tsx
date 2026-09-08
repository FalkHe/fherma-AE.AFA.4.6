// ui-spec.md §3.2. Sets the per-route document title (§7).
import { useEffect } from "react";
import { Link as RouterLink } from "react-router";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import { AuthCard } from "../components/AuthCard";
import { SignUpForm } from "../components/SignUpForm";

export function SignUpRoute() {
  const { t } = useTranslation("auth");
  const { t: tCommon } = useTranslation("common");

  useEffect(() => {
    document.title = `${t("signUp.title")} · ${tCommon("app.title")}`;
  }, [t, tCommon]);

  return (
    <AuthCard
      title={t("signUp.title")}
      footer={
        <Typography variant="body2">
          {t("signUp.haveAccount")} <Link component={RouterLink} to="/signin">{t("signUp.signInLink")}</Link>
        </Typography>
      }
    >
      <SignUpForm />
    </AuthCard>
  );
}
