import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import CardContent from "@mui/material/CardContent";
import CardMedia from "@mui/material/CardMedia";
import Chip from "@mui/material/Chip";
import Icon from "@mui/material/Icon";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router";

import type { CatalogueListItem } from "../hooks/useCatalogueModels";

import {
  formatSpecEnum,
  formatSpecValue,
  specFieldLabel,
  specFieldUnit,
} from "./specFields";

/**
 * One model in the catalogue grid (ui-spec §3.5).
 *
 * The whole surface is a real link, so middle-click and "copy link" work like
 * anywhere else. It is purely presentational: the route hands it an
 * already-fetched row, which keeps the component's tests fixture-driven and
 * makes it survive step 4.9's hook replacement untouched.
 *
 * Null discipline: a spec the extraction never found renders **nothing** — no
 * dash, no guess. On a card, unknowns are noise; the detail page is where
 * completeness matters.
 */

/** Image height; the no-image fallback matches it so card heights stay stable. */
const IMAGE_HEIGHT = 160;

/** The headline specs, in the pinned card order. */
const CARD_SPEC_FIELDS = [
  "engineCc",
  "powerKw",
  "wetWeightKg",
  "seatHeightMm",
] as const;

type CardSpecLine = { field: (typeof CARD_SPEC_FIELDS)[number]; text: string };

export function CatalogueModelCard({ model }: { model: CatalogueListItem }) {
  const { t } = useTranslation();

  const specLines = CARD_SPEC_FIELDS.map((field): CardSpecLine | null => {
    const value = formatSpecValue(t, model[field]);

    if (value === null) {
      return null;
    }
    const unit = specFieldUnit(t, field);

    return {
      field,
      text: `${specFieldLabel(t, field)}: ${value}${unit === "" ? "" : ` ${unit}`}`,
    };
  }).filter((line): line is CardSpecLine => line !== null);

  const subtitle = [
    model.manufacturer,
    model.category === null ? null : formatSpecEnum(t, "category", model.category),
  ]
    .filter((part): part is string => part !== null)
    .join(" · ");

  return (
    <Card variant="outlined" sx={{ height: "100%" }}>
      <CardActionArea
        component={RouterLink}
        to={`/catalogue/${model.motorbikeId}`}
        sx={{ height: "100%" }}
      >
        {model.image === null ? (
          // Models may be published without an approved image.
          <Box
            sx={{
              height: IMAGE_HEIGHT,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              bgcolor: "action.hover",
            }}
          >
            <Icon sx={{ fontSize: 48, color: "text.secondary" }}>two_wheeler</Icon>
          </Box>
        ) : (
          <CardMedia
            component="img"
            height={IMAGE_HEIGHT}
            image={model.image.card}
            srcSet={`${model.image.thumb} 320w, ${model.image.card} 640w`}
            sizes="(max-width: 600px) 100vw, 280px"
            alt={model.name}
            loading="lazy"
            sx={{ objectFit: "cover" }}
          />
        )}
        <CardContent>
          <Typography variant="subtitle1" component="h2" noWrap>
            {model.name}
          </Typography>
          {subtitle !== "" && (
            <Typography variant="body2" color="text.secondary" noWrap>
              {subtitle}
            </Typography>
          )}
          {model.priceBand !== null && (
            <Chip
              size="small"
              variant="outlined"
              sx={{ mt: 1 }}
              label={formatSpecEnum(t, "priceBand", model.priceBand)}
            />
          )}
          {specLines.map((line) => (
            <Typography
              key={line.field}
              variant="caption"
              color="text.secondary"
              display="block"
            >
              {line.text}
            </Typography>
          ))}
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
