// The app frame every route renders inside (docs/design/dnd-app-dashboard-
// design/project/Dashboard.dc.html:15-34). Lives in `core/` because two
// modules now render it — `core/` may import only other `core/` code plus
// third-party packages, never a module (structure test, sprint 007/04 WI2).
// Its only inputs are `action` and `children`: the product name is read
// straight off the `common:app.title` i18next key, so no caller passes a
// title anymore.
//
// Layout (creation-chat viewport fix): the shell is a `100dvh`-minimum flex
// column so `main` fills whatever the bar leaves, and every route keeps
// scrolling the page exactly as before. A route that must fit the viewport
// instead (the transcript scrolls, the composer never leaves the screen)
// marks its own root `data-fit-viewport`; `:has()` picks that up here, so
// `core/` caps the shell at `100dvh` without knowing which module asked.
import type { ReactElement, ReactNode } from "react";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import { Flame } from "lucide-react";
import { useTranslation } from "react-i18next";

export interface AppShellProps {
  action?: ReactNode;
  children: ReactNode;
}

export function AppShell({ action, children }: AppShellProps): ReactElement {
  const { t } = useTranslation("common");

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        minHeight: "100dvh",
        "&:has([data-fit-viewport])": {
          height: "100dvh",
          // Only here do `main` and the Container shrink to the space left
          // under the bar (`1 1 0` + `minHeight: 0`), so the marked child can
          // size itself to that remainder; `overflow: hidden` keeps the page
          // itself from ever scrolling.
          "& > main": { flex: "1 1 0", minHeight: 0, overflow: "hidden" },
          "& > main > .MuiContainer-root": { flex: "1 1 0", minHeight: 0 },
        },
      }}
    >
      {/* `AppBar` defaults its root to a `<header>` (MUI source), which the
          browser exposes as the `banner` landmark as long as it isn't nested
          inside `article`/`aside`/`main`/`nav`/`section` — true here, so no
          explicit `role` is needed. `position="sticky"` matches the design's
          sticky hairline bar; MUI's own sticky styles already pin `top: 0`. */}
      <AppBar
        position="sticky"
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
          <Stack direction="row" spacing={4} sx={{ alignItems: "center", flexGrow: 1, minWidth: 0 }}>
            {/* The flame mark: a pill badge in the quiet accent fill,
                carrying the house "flame" glyph (design readme.md
                "Iconography" — flame is the DM / lantern icon; "Buttons and
                badges are full pills" — "Corners"). Decorative only, the
                wordmark beside it already names the product, so it is
                hidden from the accessibility tree. */}
            <Box
              aria-hidden
              sx={(theme) => ({
                display: "grid",
                placeItems: "center",
                width: theme.spacing(8),
                height: theme.spacing(8),
                flexShrink: 0,
                borderRadius: theme.shape.borderRadiusPill,
                backgroundColor: theme.palette.action.selected,
                color: theme.palette.primary.light,
              })}
            >
              <Flame size={18} />
            </Box>
            <Typography
              // Branding, not the document heading (ui-spec.md §3.3): a
              // screen-reader user must not meet a stray heading on every
              // page just because the brand name sits in the bar.
              component="p"
              noWrap
              sx={{
                // The brand name is set in the small-caps face wherever a
                // mark would go — there is no logo (design readme.md
                // "Iconography").
                fontFamily: "var(--font-smallcaps)",
                letterSpacing: "var(--ls-label)",
              }}
            >
              {t("app.title")}
            </Typography>
          </Stack>
          {action}
        </Toolbar>
      </AppBar>
      {/* `1 0 auto` outside a fit-viewport page: `main` and the Container
          grow to fill the viewport but never shrink below their content, so
          the page scrolls just as it did before the shell became a flex
          column. */}
      <Box component="main" sx={{ display: "flex", flexDirection: "column", flex: "1 0 auto" }}>
        {/* No token in `theme/tokens/spacing.css` matches the design's 1080px
            content width (`--width-prose`/`--width-chat`/`--width-rail` are
            64ch/760px/296px, none of them this), so the pixel value is set
            directly here rather than invented as a new token — MUI's
            `maxWidth` prop only accepts a breakpoint key, not an arbitrary
            length, hence `false` plus an `sx` override
            (docs/design/.../CampaignRun.dc.html:23; sprint 007/05 WI1). */}
        <Container maxWidth={false} sx={{ py: 4, maxWidth: 1080, display: "flex", flexDirection: "column", flex: "1 0 auto" }}>
          {children}
        </Container>
      </Box>
    </Box>
  );
}
