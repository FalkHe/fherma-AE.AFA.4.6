import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, Outlet, useLocation } from "react-router";

import { LiveConnectionAlert } from "./LiveConnectionAlert";

/**
 * Chrome for the `/admin` subtree, rendered into `AppLayout`'s outlet: a
 * heading plus a secondary tab bar. Admin has one section — the review screen
 * is a drill-down of the backlog, not a section of its own — so the single tab
 * stays selected across `/admin` and `/admin/models/:id`.
 */
export function AdminLayout() {
  const { t } = useTranslation();
  const { pathname } = useLocation();

  // Prefix match rather than an exact path: every admin screen is reached from
  // the backlog, so the tab must stay lit on the review drill-down too.
  const tabValue = pathname.startsWith("/admin") ? "backlog" : false;

  return (
    <>
      <Typography variant="h4" component="h1" gutterBottom>
        {t("admin.title")}
      </Typography>
      <Tabs
        value={tabValue}
        variant="scrollable"
        allowScrollButtonsMobile
        sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}
      >
        <Tab
          value="backlog"
          label={t("admin.tabs.backlog")}
          component={RouterLink}
          to="/admin"
        />
      </Tabs>
      <LiveConnectionAlert />
      <Outlet />
    </>
  );
}
