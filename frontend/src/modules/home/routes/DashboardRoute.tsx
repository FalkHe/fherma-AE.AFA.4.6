// Sprint 007/04's second protected address (AC2's precondition) — an empty
// page behind the shared guard, a heading only. Sprint 007 fills it with
// real content.
import { useEffect } from "react";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

export function DashboardRoute() {
  const { t } = useTranslation("home");
  const { t: tCommon } = useTranslation("common");

  useEffect(() => {
    document.title = `${t("dashboard.title")} · ${tCommon("app.title")}`;
  }, [t, tCommon]);

  return (
    <Typography variant="h2" component="h1">
      {t("dashboard.title")}
    </Typography>
  );
}
