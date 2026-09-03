import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import { formatSpecValue, specFieldUnit } from "./specFields";
import type { CatalogueSearchHit, CatalogueSearchResult } from "./toolResults";

/**
 * What the advisor found in the catalogue (ui-spec §8.2).
 *
 * Names are plain text on purpose: the catalogue detail page does not exist
 * until Phase 4, and a dead link is worse than none. Only verified values are
 * shown — a hit whose specs were never extracted simply carries no fragments
 * instead of a guessed number.
 */

/** Beyond this the block would drown the answer it is supporting. */
const DISPLAY_LIMIT = 8;

export function ToolResultCatalogueSearch({ result }: { result: CatalogueSearchResult }) {
  const { t } = useTranslation();

  if (result.results.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t("consultations.tools.catalogueSearch.noResults")}
      </Typography>
    );
  }

  const shown = result.results.slice(0, DISPLAY_LIMIT);
  const remaining = result.results.length - shown.length;

  /** Up to three compact fragments — category, power, weight — when verified. */
  function specSummary(hit: CatalogueSearchHit): string {
    const category = formatSpecValue(t, hit.category);
    const powerKw = formatSpecValue(t, hit.powerKw);
    const wetWeightKg = formatSpecValue(t, hit.wetWeightKg);

    return [
      category,
      powerKw === null ? null : `${powerKw} ${specFieldUnit(t, "powerKw")}`,
      wetWeightKg === null ? null : `${wetWeightKg} ${specFieldUnit(t, "wetWeightKg")}`,
    ]
      .filter((fragment): fragment is string => fragment !== null)
      .join(" · ");
  }

  return (
    <>
      <List dense disablePadding>
        {shown.map((hit) => {
          const summary = specSummary(hit);

          return (
            <ListItem key={hit.motorbikeId} disableGutters sx={{ py: 0.25 }}>
              <ListItemText
                primary={hit.name}
                secondary={summary === "" ? undefined : summary}
                slotProps={{ primary: { variant: "body2" } }}
              />
            </ListItem>
          );
        })}
      </List>
      {remaining > 0 && (
        <Typography variant="caption" color="text.secondary">
          {t("consultations.tools.catalogueSearch.more", { count: remaining })}
        </Typography>
      )}
    </>
  );
}
