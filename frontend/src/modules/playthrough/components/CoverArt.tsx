// Shared cover-art placeholder (sprint 007/07 WI1, lifted in sprint 007/09
// WI1): the same gradient-and-label box `CampaignCard` always rendered,
// pulled out so `SelectCampaignDialog`'s catalogue cards reuse it instead of
// duplicating the placeholder markup. `sx` lets a caller override the fixed
// box (width/height) for a different layout; the gradient, border and label
// stay identical everywhere.
import type { ReactElement } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { SxProps, Theme } from "@mui/material/styles";
import { useTranslation } from "react-i18next";

export interface CoverArtProps {
  sx?: SxProps<Theme>;
}

export function CoverArt({ sx }: CoverArtProps): ReactElement {
  const { t } = useTranslation("playthrough");

  return (
    <Box
      aria-hidden
      sx={[
        (theme) => ({
          width: { xs: "100%", sm: 170 },
          height: { xs: 120, sm: 112 },
          flex: "0 0 auto",
          borderRadius: theme.shape.borderRadiusOrganicSoft,
          display: "grid",
          placeItems: "center",
          border: "1px solid var(--border-soft)",
          background: "linear-gradient(155deg, var(--loam-700), var(--bark-900) 60%, var(--loam-900))",
        }),
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    >
      <Typography variant="overline" sx={{ color: "var(--text-faint)" }}>
        {t("dashboard.card.coverArtPlaceholder")}
      </Typography>
    </Box>
  );
}
