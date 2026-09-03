import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Icon from "@mui/material/Icon";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { CatalogueImage } from "../hooks/useCatalogueModel";

/**
 * The model's approved photographs (ui-spec §4.2).
 *
 * Two decisions carry the whole component. The main image is `contain`, not
 * `cover`: cropping a motorcycle silhouette destroys the very information the
 * reader came for, and the `action.hover` letterbox keeps the block solid.
 * And its height is fixed per breakpoint — switching images, or having no image
 * at all, must never move the rest of the page.
 *
 * Attribution is shown verbatim whenever the selected image carries one: that is
 * a licence obligation, not decoration.
 *
 * Purely presentational — the route hands it already-fetched images, so it
 * survives step 4.9's hook replacement untouched.
 */

/**
 * Image, fallback and the route's loading skeleton all use this height (pinned
 * in ui-spec §4.2/§4.6), so the block keeps its shape through every state.
 */
const GALLERY_HEIGHT = { xs: 240, md: 400 } as const;

const THUMB_SIZE = 64;

export function ModelImageGallery({
  images,
  name,
}: {
  images: CatalogueImage[];
  name: string;
}) {
  const { t } = useTranslation();
  const [selectedIndex, setSelectedIndex] = useState(0);

  // A refetch can shorten the list under a selection made against the old one.
  const index = Math.min(selectedIndex, Math.max(images.length - 1, 0));
  const selected = images.at(index);

  return (
    <Box role="group" aria-label={t("catalogue.detail.galleryLabel", { name })}>
      {selected === undefined ? (
        // Models may be published without an approved image.
        <Box
          sx={{
            height: GALLERY_HEIGHT,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            bgcolor: "action.hover",
            borderRadius: 1,
          }}
        >
          <Icon sx={{ fontSize: 64, color: "text.secondary" }}>two_wheeler</Icon>
        </Box>
      ) : (
        <Box
          component="img"
          src={selected.detail}
          srcSet={`${selected.card} 640w, ${selected.detail} 1280w`}
          sizes="(max-width: 900px) 100vw, 480px"
          alt={name}
          sx={{
            width: "100%",
            height: GALLERY_HEIGHT,
            objectFit: "contain",
            bgcolor: "action.hover",
            borderRadius: 1,
          }}
        />
      )}
      {images.length > 1 && (
        <Stack direction="row" spacing={1} sx={{ mt: 1, overflowX: "auto" }}>
          {images.map((image, thumbIndex) => (
            <ButtonBase
              key={image.thumb}
              aria-label={t("catalogue.detail.imageThumbLabel", {
                index: thumbIndex + 1,
              })}
              aria-pressed={thumbIndex === index}
              onClick={() => setSelectedIndex(thumbIndex)}
            >
              <Box
                component="img"
                src={image.thumb}
                alt=""
                loading="lazy"
                sx={{
                  width: THUMB_SIZE,
                  height: THUMB_SIZE,
                  objectFit: "cover",
                  borderRadius: 1,
                  // The selection is a border *and* the pressed state — never
                  // colour alone.
                  border: 2,
                  borderColor: thumbIndex === index ? "primary.main" : "transparent",
                }}
              />
            </ButtonBase>
          ))}
        </Stack>
      )}
      {selected !== undefined && selected.attribution !== null && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ mt: 0.5, display: "block" }}
        >
          {selected.attribution}
        </Typography>
      )}
    </Box>
  );
}
