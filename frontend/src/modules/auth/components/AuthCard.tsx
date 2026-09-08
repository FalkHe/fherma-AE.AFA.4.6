// The shared frame for both auth screens (ui-spec.md §2). Two callers,
// SignInRoute and SignUpRoute, both inside modules/auth — D1's "two module
// callers" bar does not apply, so this stays here rather than promoting to
// src/components/.
import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

export interface AuthCardProps {
  title: string;
  children: ReactNode;
  footer: ReactNode;
}

export function AuthCard({ title, children, footer }: AuthCardProps) {
  const { t } = useTranslation("common");

  return (
    <Box
      sx={{
        minHeight: "100dvh",
        display: "flex",
        alignItems: { xs: "flex-start", sm: "center" },
        justifyContent: "center",
        py: { xs: 4, sm: 0 },
      }}
    >
      <Container maxWidth="xs">
        <Typography variant="h6" component="p" align="center" sx={{ mb: 2 }}>
          {t("app.title")}
        </Typography>
        <Paper elevation={1} sx={{ p: { xs: 2, sm: 3 } }}>
          <Stack spacing={2}>
            <Typography variant="h5" component="h1">
              {title}
            </Typography>
            {children}
            <Divider flexItem />
            {footer}
          </Stack>
        </Paper>
      </Container>
    </Box>
  );
}
