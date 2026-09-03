import Icon from "@mui/material/Icon";
import Link from "@mui/material/Link";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { ModelSource } from "../hooks/useCatalogueModel";

/**
 * Where this page's facts come from (ui-spec §4.5) — the out-of-chat provenance
 * surface.
 *
 * **Always expanded, never collapsible.** In the chat the sources sit behind a
 * toggle because they compete with the conversation; here they *are* one of the
 * page's contents, and burying them would defeat the purpose of showing a
 * customer which retrieved documents a recommendation rests on.
 *
 * Titles are retrieved content and render verbatim; every URL is an external
 * link that never navigates the SPA, and a document without a URL (an upload) is
 * plain text rather than a dead link. Zero sources is stated rather than hidden:
 * missing provenance is itself information.
 */

/**
 * The host of a source URL, or `null` when there is nothing parseable — the URL
 * comes from an ingested document, so it is not trusted to be absolute.
 */
function hostnameOf(sourceUrl: string): string | null {
  try {
    return new URL(sourceUrl).hostname;
  } catch {
    return null;
  }
}

/**
 * One row per distinct URL: the same page can reach the catalogue through more
 * than one document (a re-ingestion, a mirror). URL-less uploads are never
 * folded together — each is its own document.
 */
function deduplicate(sources: ModelSource[]): ModelSource[] {
  const seen = new Set<string>();

  return sources.filter((source) => {
    if (source.sourceUrl === null) {
      return true;
    }
    if (seen.has(source.sourceUrl)) {
      return false;
    }
    seen.add(source.sourceUrl);

    return true;
  });
}

export function ModelSources({ sources }: { sources: ModelSource[] }) {
  const { t } = useTranslation();

  const unique = deduplicate(sources);

  return (
    <Paper variant="outlined" sx={{ p: 2, mt: 4 }}>
      <Typography variant="h5" component="h2">
        {t("catalogue.detail.sourcesHeading")}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {t("catalogue.detail.sourcesHint")}
      </Typography>
      {unique.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t("catalogue.detail.sourcesEmpty")}
        </Typography>
      ) : (
        <List dense disablePadding aria-label={t("catalogue.detail.sourcesLabel")}>
          {unique.map((source, index) => (
            <ListItem
              key={source.sourceUrl ?? `upload-${index}`}
              disableGutters
              sx={{ py: 0 }}
            >
              <ListItemText
                primary={
                  source.sourceUrl === null ? (
                    source.sourceTitle
                  ) : (
                    <Link
                      href={source.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      variant="body2"
                    >
                      {source.sourceTitle} <Icon fontSize="inherit">open_in_new</Icon>
                    </Link>
                  )
                }
                secondary={
                  source.sourceUrl === null
                    ? t("catalogue.detail.sourceNoUrl")
                    : (hostnameOf(source.sourceUrl) ?? undefined)
                }
                slotProps={{ primary: { variant: "body2" } }}
              />
            </ListItem>
          ))}
        </List>
      )}
    </Paper>
  );
}
