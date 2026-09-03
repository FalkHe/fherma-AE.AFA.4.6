import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Grid from "@mui/material/Grid";
import Link from "@mui/material/Link";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { useProductDocuments, type SourceDocument } from "../hooks/useProductReview";
import type { Product } from "../hooks/useProducts";

import { EmptyState } from "./EmptyState";
import { UntrustedMarkdown } from "./UntrustedMarkdown";

/**
 * The Documents tab: every source the ingestion retained, with its provenance
 * and its normalized Markdown.
 *
 * Showing the retrieved context — title, type, URL and fetch date next to the
 * text the extraction actually read — is a graded requirement, not a nicety, so
 * the provenance line is always rendered and the source URL is shown in full.
 *
 * Retrieved prose is untrusted content: it renders through the shared
 * `UntrustedMarkdown` component (GFM tables, strikethrough, **raw HTML
 * off**), so any markup inside a fetched page appears as text. Links inside
 * the Markdown open in a new tab instead of navigating the SPA.
 */

/**
 * Typography for the rendered Markdown, merged after `UntrustedMarkdown`'s
 * base sx: an inline image must not push the layout. Palette tokens only.
 */
const MARKDOWN_SX = {
  "& img": { maxWidth: "100%", height: "auto" },
} as const;

/**
 * Retrieved documents carry Wikipedia-width tables whose min-content width is
 * far past a phone viewport; unwrapped they push the whole page sideways
 * (ui-spec §10 — "no horizontal page scroll anywhere" at 360px). The wrapper
 * bounds the table to the column and moves the overflow into its own
 * scroller (mirrors `CatalogueModelRoute`'s `ProseTable` — module-local per
 * the per-site delta rule, ui-spec §4).
 */
function DocProseTable({ children }: { children?: ReactNode }) {
  return (
    <Box sx={{ maxWidth: "100%", overflowX: "auto" }}>
      <table>{children}</table>
    </Box>
  );
}

const MARKDOWN_COMPONENTS = {
  table: DocProseTable,
};

/** `example.org` out of a source URL; the raw value if it will not parse. */
function hostname(sourceUrl: string): string {
  try {
    return new URL(sourceUrl).hostname;
  } catch {
    return sourceUrl;
  }
}

export function ModelDocumentsPanel({ product }: { product: Product }) {
  const { t, i18n } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const documents = useProductDocuments(product.id);

  const rows = documents.data;
  const selectedId = searchParams.get("doc");
  // Absent or unknown selects the first document (the API delivers Wikipedia
  // first), so a stale `doc` param never shows an empty pane.
  const selected: SourceDocument | undefined =
    rows?.find((row) => row.id === selectedId) ?? rows?.at(0);

  const staleSelection =
    selectedId !== null && selected !== undefined && selected.id !== selectedId;

  useEffect(() => {
    if (!staleSelection || selected === undefined) {
      return;
    }

    // The param pointed at a document that is gone: rewrite it to what is
    // actually on screen, so a reload or a shared link stays honest.
    const params = new URLSearchParams(searchParams);

    params.set("doc", selected.id);
    setSearchParams(params, { replace: true });
  }, [staleSelection, selected, searchParams, setSearchParams]);

  function select(documentId: string) {
    const params = new URLSearchParams(searchParams);

    params.set("doc", documentId);
    // View state: the back button must leave the page, not unwind a series of
    // document clicks.
    setSearchParams(params, { replace: true });
  }

  // The route only gates the product query — this panel owns its own
  // documents query's loading and error states, so a failed tab is never
  // indistinguishable from an empty one.
  if (documents.isError) {
    return (
      <EmptyState
        icon="error"
        title={t("admin.review.documents.loadError")}
        body={t("common.errors.serverError")}
        action={
          <Button
            onClick={() => {
              void documents.refetch();
            }}
          >
            {t("common.retry")}
          </Button>
        }
      />
    );
  }

  if (rows === undefined) {
    return (
      <Box
        role="status"
        aria-label={t("common.loading")}
        sx={{ display: "flex", justifyContent: "center", py: 8 }}
      >
        <CircularProgress size={48} />
      </Box>
    );
  }

  if (rows.length === 0 || selected === undefined) {
    return (
      <EmptyState
        icon="description"
        title={t("admin.review.documents.emptyTitle")}
        body={t("admin.review.documents.emptyBody")}
      />
    );
  }

  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, md: 4 }}>
        <Paper variant="outlined">
          <List aria-label={t("admin.review.documents.listLabel")} disablePadding>
            {rows.map((row) => (
              <ListItemButton
                key={row.id}
                selected={row.id === selected.id}
                onClick={() => select(row.id)}
              >
                <ListItemText
                  primary={row.sourceTitle}
                  secondary={
                    t(`admin.review.documents.sourceType.${row.sourceType}`) +
                    (row.sourceUrl === null ? "" : ` · ${hostname(row.sourceUrl)}`)
                  }
                />
              </ListItemButton>
            ))}
          </List>
        </Paper>
      </Grid>
      <Grid size={{ xs: 12, md: 8 }}>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" component="h3">
            {selected.sourceTitle}
          </Typography>
          <Stack
            direction="row"
            spacing={1}
            sx={{ alignItems: "center", flexWrap: "wrap" }}
          >
            <Chip
              size="small"
              variant="outlined"
              label={t(`admin.review.documents.sourceType.${selected.sourceType}`)}
            />
            {selected.sourceUrl !== null && (
              <Link
                href={selected.sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                variant="body2"
                sx={{ wordBreak: "break-all" }}
              >
                {selected.sourceUrl}
              </Link>
            )}
            <Typography variant="caption" color="text.secondary">
              {t("admin.review.documents.fetchedAt", {
                date: new Date(selected.fetchedAt).toLocaleString(i18n.language, {
                  dateStyle: "medium",
                  timeStyle: "short",
                }),
              })}
            </Typography>
          </Stack>
          <Divider sx={{ my: 2 }} />
          <UntrustedMarkdown sx={MARKDOWN_SX} components={MARKDOWN_COMPONENTS}>
            {selected.contentMarkdown}
          </UntrustedMarkdown>
        </Paper>
      </Grid>
    </Grid>
  );
}
