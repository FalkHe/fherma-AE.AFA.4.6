import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Icon from "@mui/material/Icon";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Fragment } from "react";
import { useTranslation } from "react-i18next";

import { isUsedPrice } from "./usedPrice";

/**
 * The used-market snapshot (roadmap 6.4, ui-spec §4.1) — the "snapshot, never
 * a fact" framing shared by the catalogue detail (§4.2) and the chat cost
 * estimator (§4.3), so it cannot drift between the two surfaces.
 *
 * Presentational, data as props. Staleness is driven **only** by the payload's
 * `stale` boolean (shared-knowledge D10) — this component owns no clock and
 * must never compute a day count from `asOf`. The wire type and its malformed
 * guard live in `usedPrice.ts` (kept out of this file so it can stay a
 * component-only export, per `react-refresh/only-export-components`).
 */

export function UsedPriceSnapshot({
  usedPrice,
  currency = "EUR",
}: {
  usedPrice: unknown;
  currency?: string;
}) {
  const { t, i18n } = useTranslation();

  if (!isUsedPrice(usedPrice)) {
    return null;
  }

  const { medianEur, minEur, maxEur, sampleCount, asOf, stale, sources } = usedPrice;

  // The exact `ToolResultCostEstimator` idiom — whole euros, locale-formatted.
  const money = new Intl.NumberFormat(i18n.language, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  });
  const date = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" });

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
        <Typography variant="subtitle1">{t("common.usedPrice.heading")}</Typography>
        <Chip
          size="small"
          variant="outlined"
          color="warning"
          icon={<Icon>schedule</Icon>}
          label={t("common.usedPrice.snapshotChip")}
        />
      </Stack>
      <Typography variant="h6">
        {t("common.usedPrice.range", { min: money.format(minEur), max: money.format(maxEur) })}
      </Typography>
      <Typography variant="caption" color="text.secondary" component="p">
        {t("common.usedPrice.median", { median: money.format(medianEur) })}
        {" · "}
        {sampleCount === null
          ? t("common.usedPrice.sampleUnknown")
          : t("common.usedPrice.sampleCount", { count: sampleCount })}
      </Typography>
      <Typography variant="caption" color="text.secondary" component="p">
        {t("common.usedPrice.disclaimer")}
      </Typography>
      <Typography variant="caption" color="text.secondary" component="p">
        {t("common.usedPrice.sources")}:{" "}
        {sources.map((source, index) => (
          <Fragment key={source.url}>
            {index > 0 && " · "}
            <Link href={source.url} target="_blank" rel="noopener noreferrer" variant="caption">
              {source.title} <Icon fontSize="inherit">open_in_new</Icon>
            </Link>
          </Fragment>
        ))}
        {" — "}
        {t("common.usedPrice.asOf", { date: date.format(new Date(asOf)) })}
      </Typography>
      {stale && (
        <Typography
          variant="caption"
          color="warning.main"
          component="p"
          sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.5 }}
        >
          <Icon fontSize="small">history</Icon>
          {t("common.usedPrice.stale")}
        </Typography>
      )}
    </Box>
  );
}
