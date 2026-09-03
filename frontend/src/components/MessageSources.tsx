import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Icon from "@mui/material/Icon";
import Link from "@mui/material/Link";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { MessageSource } from "../hooks/useChatMessages";

/**
 * Where the answer came from (ui-spec §7) — the receipts.
 *
 * Collapsed by default, but the toggle always shows the **count**: provenance
 * has to be discoverable at a glance without pushing the conversation off the
 * screen. Titles are retrieved content and render verbatim; every source is an
 * external link, because retrieved-content links must never navigate the SPA.
 */

/**
 * The backend already dedupes by source document, but two documents can share a
 * URL, and the same page can be cited through several chunks. What the reader
 * cares about is the distinct place a claim came from: URL plus heading path.
 */
function deduplicate(sources: MessageSource[]): MessageSource[] {
  const seen = new Set<string>();

  return sources.filter((source) => {
    const key = `${source.sourceUrl ?? ""}|${source.headingPath ?? ""}`;

    if (seen.has(key)) {
      return false;
    }
    seen.add(key);

    return true;
  });
}

/**
 * The host of a source URL, or `null` when there is nothing parseable — the URL
 * comes from an ingested document, so it is not trusted to be absolute.
 */
function hostnameOf(sourceUrl: string | null): string | null {
  if (sourceUrl === null) {
    return null;
  }
  try {
    return new URL(sourceUrl).hostname;
  } catch {
    return null;
  }
}

/** "Suzuki GSR600 > Design" → "Suzuki GSR600 › Design". */
function formatHeadingPath(headingPath: string): string {
  return headingPath
    .split(">")
    .map((segment) => segment.trim())
    .filter((segment) => segment !== "")
    .join(" › ");
}

function sourceSecondary(source: MessageSource): string {
  const parts = [hostnameOf(source.sourceUrl)];

  if (source.headingPath !== null && source.headingPath !== "") {
    parts.push(formatHeadingPath(source.headingPath));
  }

  return parts.filter((part): part is string => part !== null).join(" · ");
}

export function MessageSources({ sources }: { sources: MessageSource[] }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const unique = deduplicate(sources);

  if (unique.length === 0) {
    return null;
  }

  return (
    <>
      <Divider sx={{ my: 1 }} />
      <Button
        size="small"
        color="inherit"
        onClick={() => setExpanded((open) => !open)}
        aria-expanded={expanded}
        startIcon={
          <Icon
            sx={{
              transform: expanded ? "rotate(180deg)" : "none",
              transition: "transform 150ms",
            }}
          >
            expand_more
          </Icon>
        }
      >
        {t("consultations.chat.sourcesToggle", { count: unique.length })}
      </Button>
      <Collapse in={expanded}>
        <List dense disablePadding aria-label={t("consultations.chat.sourcesLabel")}>
          {unique.map((source) => {
            const secondary = sourceSecondary(source);

            return (
              <ListItem key={source.chunkId} disableGutters sx={{ py: 0 }}>
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
                  secondary={secondary === "" ? undefined : secondary}
                  slotProps={{ primary: { variant: "body2" } }}
                />
              </ListItem>
            );
          })}
        </List>
      </Collapse>
    </>
  );
}
