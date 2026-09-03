import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, useParams } from "react-router";

import { EmptyState } from "../components/EmptyState";
import { ModelImageGallery } from "../components/ModelImageGallery";
import { ModelSources } from "../components/ModelSources";
import { ModelSpecTable } from "../components/ModelSpecTable";
import { formatSpecEnum } from "../components/specFields";
import { UntrustedMarkdown } from "../components/UntrustedMarkdown";
import { isUsedPrice } from "../components/usedPrice";
import { UsedPriceSnapshot } from "../components/UsedPriceSnapshot";
import { CatalogueError, useCatalogueModel } from "../hooks/useCatalogueModel";

/**
 * One model, everything the catalogue knows about it (ui-spec §4): photographs,
 * the verified specification, the retrieved prose and — always visible — the
 * documents all of it came from.
 *
 * The page is read-only and self-contained: one request delivers specs, article,
 * sources and images, and each block degrades on its own, so a model without an
 * image, without prose or without a verified spec still renders a complete page
 * rather than a hole. An unknown **or unpublished** id answers 404 and gets the
 * one not-found state — the backend deliberately cannot tell the two apart, and
 * neither does this screen.
 *
 * The article is retrieved web content, so it goes through the shared
 * `UntrustedMarkdown` renderer with **raw HTML off** (never add `rehype-raw`)
 * — the same rule as the chat bubbles, and the named domain security measure
 * for this surface.
 */

/**
 * The article's own headings are demoted: the page already owns its `h1` (the
 * model name) and its `h2`s (the sections), so a retrieved `##` becomes an `h3`
 * and everything below it an `h4`. Retrieved content cannot be trusted to keep a
 * sane outline, and the outline is what a screen reader navigates by.
 */
function ProseHeading3({ children }: { children?: ReactNode }) {
  return (
    <Typography variant="h6" component="h3" sx={{ mt: 3, mb: 1 }}>
      {children}
    </Typography>
  );
}

function ProseHeading4({ children }: { children?: ReactNode }) {
  return (
    <Typography variant="subtitle1" component="h4" sx={{ mt: 2, mb: 0.5 }}>
      {children}
    </Typography>
  );
}

/**
 * Retrieved articles carry Wikipedia-width tables whose min-content width is
 * far past a phone viewport; unwrapped they push the whole page sideways
 * (ui-spec §10 — "no horizontal page scroll anywhere" at 360px). The wrapper
 * bounds the table to the column and moves the overflow into its own scroller.
 */
function ProseTable({ children }: { children?: ReactNode }) {
  return (
    <Box sx={{ maxWidth: "100%", overflowX: "auto" }}>
      <table>{children}</table>
    </Box>
  );
}

const MARKDOWN_COMPONENTS = {
  table: ProseTable,
  h1: ProseHeading3,
  h2: ProseHeading3,
  h3: ProseHeading4,
  h4: ProseHeading4,
  h5: ProseHeading4,
  h6: ProseHeading4,
};

/**
 * Typography for the rendered article, merged after `UntrustedMarkdown`'s
 * base sx: an inline image must not push the layout (a wide table scrolls
 * inside the `ProseTable` wrapper above). Palette tokens only.
 */
const MARKDOWN_SX = {
  "& p": { my: 1 },
  "& img": { maxWidth: "100%" },
} as const;

const SKELETON_SPEC_ROWS = 8;

/**
 * The gallery slot's height, pinned by ui-spec §4.2/§4.6 for both the gallery
 * and this skeleton — the loading page must have the exact shape of the loaded
 * one, so nothing jumps when the request lands.
 */
const SKELETON_GALLERY_HEIGHT = { xs: 240, md: 400 } as const;

export function CatalogueModelRoute() {
  const { t } = useTranslation();
  const { motorbikeId = "" } = useParams();
  const model = useCatalogueModel(motorbikeId);

  const backLink = (
    <Link component={RouterLink} to="/catalogue">
      {t("catalogue.detail.back")}
    </Link>
  );

  if (model.isPending) {
    // Every slot keeps the size of the content that replaces it, so the page
    // does not jump when the request lands.
    return (
      <>
        <Breadcrumbs sx={{ mb: 2 }}>
          {backLink}
          <Skeleton width={140} />
        </Breadcrumbs>
        <Skeleton variant="text" width="40%" height={48} />
        <Grid container spacing={4} sx={{ mt: 1 }}>
          <Grid size={{ xs: 12, md: 5 }}>
            <Skeleton variant="rounded" sx={{ height: SKELETON_GALLERY_HEIGHT }} />
          </Grid>
          <Grid size={{ xs: 12, md: 7 }}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              {Array.from({ length: SKELETON_SPEC_ROWS }, (_unused, index) => (
                <Skeleton key={index} variant="text" />
              ))}
            </Paper>
          </Grid>
        </Grid>
      </>
    );
  }

  if (model.isError || model.data === undefined) {
    const status = model.error instanceof CatalogueError ? model.error.status : 0;
    const backToCatalogue = (
      <Button component={RouterLink} to="/catalogue">
        {t("catalogue.detail.back")}
      </Button>
    );

    // 404 covers both the unknown id and the model that is not published — the
    // target of a stale recommendation-card link.
    if (status === 404) {
      return (
        <EmptyState
          icon="search_off"
          title={t("catalogue.detail.notFoundTitle")}
          body={t("catalogue.detail.notFoundBody")}
          action={backToCatalogue}
        />
      );
    }

    return (
      <EmptyState
        icon="error"
        title={t("catalogue.detail.loadError")}
        body={t("common.errors.serverError")}
        action={
          <Button
            onClick={() => {
              void model.refetch();
            }}
          >
            {t("common.retry")}
          </Button>
        }
      />
    );
  }

  const { name, manufacturer, specs, article, sources, images, variants, usedPrice } =
    model.data;

  return (
    <>
      <Breadcrumbs sx={{ mb: 2 }}>
        {backLink}
        <Typography color="text.primary" noWrap>
          {name}
        </Typography>
      </Breadcrumbs>
      <Typography variant="h4" component="h1">
        {name}
      </Typography>
      {variants !== undefined && variants.length > 0 && (
        // The trims chip row (ui-spec §3.2, display-spec §6.5) — directly
        // under the `h1`, one outlined `Chip` per entry, description as a
        // `Tooltip`; the chips are labels, they link nowhere.
        <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: "wrap" }}>
          {variants.map((variant) =>
            variant.description != null && variant.description !== "" ? (
              <Tooltip key={variant.slug} title={variant.description} describeChild>
                <Chip variant="outlined" label={variant.name} />
              </Tooltip>
            ) : (
              <Chip key={variant.slug} variant="outlined" label={variant.name} />
            ),
          )}
        </Stack>
      )}
      <Stack
        direction="row"
        spacing={1}
        sx={{ mt: 1, mb: 3, alignItems: "center", flexWrap: "wrap" }}
      >
        {manufacturer !== null && (
          <Typography variant="subtitle1" color="text.secondary">
            {manufacturer}
          </Typography>
        )}
        {specs.category !== null && (
          <Chip size="small" label={formatSpecEnum(t, "category", specs.category)} />
        )}
        {specs.priceBand !== null && (
          <Chip
            size="small"
            variant="outlined"
            label={formatSpecEnum(t, "priceBand", specs.priceBand)}
          />
        )}
        {/* Only a verified `true` earns the badge; unknown is never a claim. */}
        {specs.a2Eligible === true && (
          <Chip
            size="small"
            color="success"
            variant="outlined"
            label={t("consultations.specFields.a2Eligible")}
          />
        )}
      </Stack>
      <Grid container spacing={4}>
        <Grid size={{ xs: 12, md: 5 }}>
          <ModelImageGallery images={images} name={name} />
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          <ModelSpecTable specs={specs} variants={variants} />
        </Grid>
      </Grid>
      {isUsedPrice(usedPrice) && (
        // Used-market snapshot (ui-spec §4.2) — full-width, between the
        // image/spec Grid and the About article. Absent (`null` or member
        // missing) renders nothing at all: no heading, no "no price yet" line.
        <Paper variant="outlined" sx={{ p: 2, mt: 4 }}>
          <UsedPriceSnapshot usedPrice={usedPrice} />
        </Paper>
      )}
      {article !== null && (
        <>
          <Typography variant="h5" component="h2" sx={{ mt: 4, mb: 1 }}>
            {t("catalogue.detail.aboutHeading")}
          </Typography>
          <UntrustedMarkdown sx={MARKDOWN_SX} components={MARKDOWN_COMPONENTS}>
            {article}
          </UntrustedMarkdown>
        </>
      )}
      <ModelSources sources={sources} />
    </>
  );
}
