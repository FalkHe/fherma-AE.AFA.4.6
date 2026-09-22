// The header's one entry point into the signed-in account: a round trigger
// carrying the user's initial, opening a menu with the username, a hairline
// and "Sign out" (AC3, docs/design/.../Dashboard.dc.html:15-34). Owns both
// `useCurrentUser()` and `useSignOut()` itself — nothing is passed in — so
// no caller has to wire either through; this is what shrinks the
// `home -> auth` import edge down to `useCurrentUser` alone (see
// modules/home/README.md).
//
// A refused sign-out (403/5xx) surfaces `signOut.error` as an alert inside
// the still-open menu rather than closing it — the user needs to see why
// nothing happened without losing the menu they were just using. A 401 is
// already folded into `useSignOut`'s success path (an expired session signs
// out silently), so no separate handling is needed here.
import { useState, type MouseEvent } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { LogOut } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useCurrentUser } from "../hooks/useCurrentUser";
import { useSignOut } from "../hooks/useSignOut";

export function AccountMenu() {
  const { t } = useTranslation("auth");
  const { user } = useCurrentUser();
  const signOut = useSignOut();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);

  function handleOpen(event: MouseEvent<HTMLElement>) {
    setAnchorEl(event.currentTarget);
  }

  function handleClose() {
    setAnchorEl(null);
  }

  return (
    <>
      <IconButton aria-label={t("account.open")} aria-haspopup="menu" onClick={handleOpen}>
        {user ? user.username[0].toUpperCase() : ""}
      </IconButton>
      <Menu anchorEl={anchorEl} open={open} onClose={handleClose}>
        <Box sx={{ px: 2, py: 1 }}>
          <Typography variant="h6" component="div" noWrap>
            {user?.username}
          </Typography>
        </Box>
        <Divider />
        {signOut.isError && (
          <Alert role="alert" severity="error" sx={{ mx: 1, my: 1 }}>
            {t("signOut.error")}
          </Alert>
        )}
        {/* `ListItemIcon`'s own default styles call `theme.spacing()` with a
            non-integer index — harmless against MUI's usual numeric spacing
            scale, but this theme's `spacing` is the design system's
            (non-linear) token array (core/theme/index.ts), so that call logs
            an MUI console warning here. `Stack` only ever receives the
            integer `spacing` value below, so it lays the icon and label out
            identically without tripping it. */}
        <MenuItem onClick={() => signOut.mutate()} disabled={signOut.isPending}>
          <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
            <LogOut size={16} />
            <span>{t("signOut.action")}</span>
          </Stack>
        </MenuItem>
      </Menu>
    </>
  );
}
