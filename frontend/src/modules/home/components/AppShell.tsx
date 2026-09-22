// The app frame later phases extend (ui-spec.md §3.3, step-0.1.md §6.2 R2).
// Lives here, not in src/components/, because HomeRoute is its only caller
// (D1). Imports nothing from any module and calls no hook of its own — its
// only inputs are `title`, `action` and `children` (UI-40, UI-41).
import type { ReactNode } from "react";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";

export interface AppShellProps {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}

export function AppShell({ title, action, children }: AppShellProps) {
  return (
    <>
      <AppBar
        position="static"
        elevation={0}
        // Dark mode already keeps `color` off the default "primary" fill
        // (Material Design guidance MUI follows unless `enableColorOnDark`
        // is set), so the bar reads as a neutral raised surface rather than
        // a flood of the lantern accent — no override needed here. The
        // hairline + shadow + uneven bottom edge are this system's own
        // panel treatment (design readme.md "Cards" / "Corners").
        sx={(theme) => ({
          borderBottom: `1px solid ${theme.palette.divider}`,
          borderRadius: theme.shape.borderRadiusOrganicSoft,
          boxShadow: theme.shadows[2],
        })}
      >
        <Toolbar>
          <Typography
            variant="h6"
            component="p"
            noWrap
            sx={{
              flexGrow: 1,
              // The brand name is set in the small-caps face wherever a
              // mark would go — there is no logo (design readme.md
              // "Iconography").
              fontFamily: "var(--font-smallcaps)",
              letterSpacing: "var(--ls-label)",
            }}
          >
            {title}
          </Typography>
          {action}
        </Toolbar>
      </AppBar>
      <Box component="main">
        <Container maxWidth="sm" sx={{ py: 4 }}>
          {children}
        </Container>
      </Box>
    </>
  );
}
