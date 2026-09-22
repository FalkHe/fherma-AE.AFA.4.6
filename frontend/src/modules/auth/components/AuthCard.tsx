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
        // The design system's "lantern" wash — a warm pool bleeding down
        // from a hanging lamp — reads best behind a tall, mostly-empty
        // canvas like this one (readme.md "Backgrounds").
        backgroundImage: "var(--wash-lantern)",
      }}
    >
      <Container maxWidth="xs">
        <Typography
          variant="h6"
          component="p"
          align="center"
          sx={{
            mb: 2,
            // The brand name is set in the small-caps face wherever a mark
            // would go — there is no logo (design readme.md "Iconography").
            fontFamily: "var(--font-smallcaps)",
            letterSpacing: "var(--ls-label)",
          }}
        >
          {t("app.title")}
        </Typography>
        <Paper
          elevation={6}
          sx={(theme) => ({
            p: { xs: 2, sm: 3 },
            // Panels read as hand-cut wood, not CSS boxes: an uneven
            // "organic" radius plus a one-pixel hairline border, read only
            // through the theme (never a literal) — design readme.md
            // "Corners" / "Cards".
            borderRadius: theme.shape.borderRadiusOrganic,
            border: `1px solid ${theme.palette.divider}`,
          })}
        >
          <Stack spacing={2}>
            <Typography variant="h3" component="h1">
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
