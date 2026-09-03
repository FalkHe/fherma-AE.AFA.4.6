import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import CardContent from "@mui/material/CardContent";
import CardMedia from "@mui/material/CardMedia";
import Icon from "@mui/material/Icon";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router";

import type { Recommendation } from "../hooks/useChatMessages";

import { formatSpecValue, specFieldLabel, specFieldUnit } from "./specFields";

/**
 * One recommended model (Phase-3 ui-spec §9) — the payoff of the conversation.
 *
 * The card is a **write-time snapshot**: everything it shows travelled with the
 * message, so it needs no catalogue read to render. Since Phase 4 its whole
 * surface is a real link to that model's catalogue page (Phase-4 ui-spec §6) —
 * the href contract the `motorbikeId` prop was reserved for.
 */

/** Image height; the no-image fallback matches it so card heights stay stable. */
const IMAGE_HEIGHT = 140;

/**
 * The API returns server-relative `/media/…` URLs. In development the SPA and
 * the API live on different origins, so a relative URL would resolve against
 * Vite and answer the SPA fallback instead of the image — same convention as
 * `api/client.ts` and `useProductReview`.
 */
const mediaBase: string = import.meta.env.VITE_API_URL ?? "";

/** The four key specs a card shows, in the pinned order. */
const CARD_SPEC_FIELDS = ["category", "powerKw", "wetWeightKg", "seatHeightMm"] as const;

type CardSpecLine = { field: (typeof CARD_SPEC_FIELDS)[number]; text: string };

/**
 * The persisted `imageUrl` is the **card** variant; the thumb is the same path
 * with the variant suffix swapped (shared-knowledge §"Persisted JSONB shapes").
 */
function imageVariants(imageUrl: string | null): { card: string; thumb: string } | null {
  if (imageUrl === null || imageUrl === "") {
    return null;
  }

  return {
    card: mediaBase + imageUrl,
    thumb: mediaBase + imageUrl.replace(/_card\.webp$/, "_thumb.webp"),
  };
}

export function RecommendationCard({
  recommendation,
}: {
  recommendation: Recommendation;
}) {
  const { t } = useTranslation();

  const variants = imageVariants(recommendation.imageUrl);
  const specLines = CARD_SPEC_FIELDS.map((field): CardSpecLine | null => {
    const value = formatSpecValue(t, recommendation.keySpecs[field]);

    if (value === null) {
      return null;
    }
    const unit = specFieldUnit(t, field);

    return {
      field,
      text: `${specFieldLabel(t, field)}: ${value}${unit === "" ? "" : ` ${unit}`}`,
    };
  }).filter((line): line is CardSpecLine => line !== null);

  return (
    <Card variant="outlined" sx={{ width: { xs: "100%", sm: 280 } }}>
      <CardActionArea
        component={RouterLink}
        to={`/catalogue/${recommendation.motorbikeId}`}
      >
        {variants === null ? (
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
            image={variants.card}
            srcSet={`${variants.thumb} 320w, ${variants.card} 640w`}
            sizes="280px"
            alt={recommendation.name}
            loading="lazy"
            sx={{ objectFit: "cover" }}
          />
        )}
        <CardContent>
          <Typography variant="subtitle1" component="h3">
            {recommendation.name}
          </Typography>
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
          <Typography variant="body2" sx={{ mt: 1 }}>
            {recommendation.rationale}
          </Typography>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
