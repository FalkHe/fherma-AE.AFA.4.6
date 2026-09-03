import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Container from "@mui/material/Container";
import Divider from "@mui/material/Divider";
import Icon from "@mui/material/Icon";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, Outlet, useNavigate } from "react-router";

import { useAuth, useLogout } from "../hooks/useAuth";
import { useServerEvents } from "../hooks/useServerEvents";
import { ThemeModeToggle } from "./ThemeModeToggle";

/**
 * Holds the single server-event stream for as long as somebody is signed in.
 *
 * It exists as a component rather than a call in `AppLayout` because the stream
 * must be tied to the session: rendering it conditionally is what closes the
 * connection the moment the identity cache goes empty, so a sign-out never
 * leaves an authenticated stream open behind the login screen. `/api/events`
 * requires a session anyway.
 */
function ServerEventsConnection() {
  useServerEvents();

  return null;
}

/**
 * Three text labels plus the theme toggle and the account block do not fit a
 * 360px toolbar (the hidden title alone was not enough — measured 377px of
 * content), so below `sm` each nav button degrades to its glyph: dropping the
 * button's 64px `minWidth` turns a ~137px label into a 40px target. The
 * `aria-label` carries the destination name at every width, so the icon-only
 * form is still announced and still a real link. Padding stays at the MUI
 * default, so `sm`-and-up rendering is untouched.
 */
const NAV_BUTTON_SX = {
  minWidth: { xs: 0, sm: 64 },
} as const;

const NAV_ICON_SX = { display: { xs: "block", sm: "none" } } as const;

const NAV_LABEL_SX = { display: { xs: "none", sm: "inline" } } as const;

function NavButton({ to, icon, label }: { to: string; icon: string; label: string }) {
  return (
    <Button color="inherit" component={RouterLink} to={to} aria-label={label} sx={NAV_BUTTON_SX}>
      <Icon sx={NAV_ICON_SX}>{icon}</Icon>
      <Box component="span" sx={NAV_LABEL_SX}>
        {label}
      </Box>
    </Button>
  );
}

/**
 * Chrome shared by every route: the top bar and the main content container.
 * Routes render into the `Outlet`.
 *
 * Navigation and the account menu render only for a signed-in user, which is
 * what lets the public auth pages share this layout instead of needing one of
 * their own. Two destinations do not justify a drawer, so the nav is inline in
 * the toolbar and still fits a phone.
 */
export function AppLayout() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const logout = useLogout();
  const [accountAnchorEl, setAccountAnchorEl] = useState<HTMLElement | null>(null);

  function handleSignOut() {
    // `useLogout` clears the query cache and counts a 401 as success (the
    // session is gone either way), so this callback is exactly the "settle"
    // condition of ui-spec §4. Any other failure — a stale CSRF cookie, a 5xx —
    // leaves the user where they are, still signed in as far as we know.
    logout.mutate(undefined, {
      onSuccess: () => {
        navigate("/login", { replace: true });
      },
    });
    setAccountAnchorEl(null);
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", minHeight: "100dvh" }}>
      {user !== null && <ServerEventsConnection />}
      <AppBar position="static">
        <Toolbar>
          <Typography
            variant="h6"
            component={RouterLink}
            to="/"
            sx={{
              flexGrow: 1,
              color: "inherit",
              textDecoration: "none",
              // Three nav destinations plus the account block need the whole
              // width of a phone; the page's own header identifies the app there.
              display: { xs: "none", sm: "block" },
            }}
          >
            {t("app.name")}
          </Typography>
          {/* Stands in for the hidden title, so the right-side controls keep
              their position at xs. */}
          <Box sx={{ flexGrow: 1, display: { xs: "block", sm: "none" } }} />
          {user !== null && (
            <Box sx={{ display: "flex", gap: { xs: 0.5, sm: 1 }, mr: 1 }}>
              <NavButton to="/consultations" icon="forum" label={t("nav.consultations")} />
              <NavButton to="/catalogue" icon="two_wheeler" label={t("nav.catalogue")} />
              {user.role === "admin" && (
                <NavButton
                  to="/admin"
                  icon="admin_panel_settings"
                  label={t("nav.admin")}
                />
              )}
            </Box>
          )}
          <ThemeModeToggle />
          {user !== null && (
            <>
              <Button
                color="inherit"
                aria-label={t("account.menuLabel")}
                aria-haspopup="menu"
                aria-expanded={accountAnchorEl !== null}
                startIcon={<Icon>account_circle</Icon>}
                endIcon={<Icon>arrow_drop_down</Icon>}
                onClick={(event) => setAccountAnchorEl(event.currentTarget)}
              >
                {/* Hidden on xs so the trigger degrades to icon-only; the menu
                    repeats the name for those viewports. */}
                <Box component="span" sx={{ display: { xs: "none", sm: "inline" } }}>
                  {user.username}
                </Box>
              </Button>
              <Menu
                anchorEl={accountAnchorEl}
                open={accountAnchorEl !== null}
                onClose={() => setAccountAnchorEl(null)}
                aria-label={t("account.menuLabel")}
              >
                <MenuItem disabled>
                  {t("account.signedInAs", { username: user.username })}
                </MenuItem>
                <Divider />
                <MenuItem onClick={handleSignOut} disabled={logout.isPending}>
                  <ListItemIcon>
                    <Icon fontSize="small">logout</Icon>
                  </ListItemIcon>
                  <ListItemText>{t("account.signOut")}</ListItemText>
                </MenuItem>
              </Menu>
            </>
          )}
        </Toolbar>
      </AppBar>
      <Container component="main" maxWidth="lg" sx={{ flexGrow: 1, py: 4 }}>
        <Outlet />
      </Container>
    </Box>
  );
}
