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
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" component="p" noWrap sx={{ flexGrow: 1 }}>
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
