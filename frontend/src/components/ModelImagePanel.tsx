import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Icon from "@mui/material/Icon";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  useProductImage,
  useRejectImage,
  type ImageStatus,
} from "../hooks/useProductReview";
import type { Product } from "../hooks/useProducts";

import { ConfirmDialog } from "./ConfirmDialog";
import { EmptyState } from "./EmptyState";

/**
 * The Image tab: the one image an ingestion run fetched, its smaller variants,
 * its licence — and the single moderation action this phase offers, rejecting it.
 *
 * The attribution block is rendered whenever an image exists, including the
 * "no licence metadata could be retrieved" case: showing the licence is a legal
 * requirement, not a nicety, and an image without one is exactly what an admin
 * has to judge in review.
 *
 * There is no image-approve button: approving the **model** approves a pending
 * image server-side, and a model may be published with a rejected or missing
 * image (replacement by upload is deliberately a later feature).
 */

const STATUS_COLOR: Record<ImageStatus, "warning" | "success" | "error"> = {
  pending: "warning",
  approved: "success",
  rejected: "error",
};

/** `thumb` and `card` previews, so the admin sees what the catalogue will show. */
const PREVIEW_VARIANTS = ["thumb", "card"] as const;

export function ModelImagePanel({ product }: { product: Product }) {
  const { t } = useTranslation();
  const image = useProductImage(product.id);
  const rejectImage = useRejectImage();
  const [isRejectDialogOpen, setIsRejectDialogOpen] = useState(false);

  const row = image.data;

  // The route only gates the product query — this panel owns its own image
  // query's loading and error states, so a failed tab is never
  // indistinguishable from an empty one.
  if (image.isError) {
    return (
      <EmptyState
        icon="error"
        title={t("admin.review.image.loadError")}
        body={t("common.errors.serverError")}
        action={
          <Button
            onClick={() => {
              void image.refetch();
            }}
          >
            {t("common.retry")}
          </Button>
        }
      />
    );
  }

  if (row === undefined) {
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

  if (row === null) {
    return (
      <EmptyState
        icon="image"
        title={t("admin.review.image.emptyTitle")}
        body={t("admin.review.image.emptyBody")}
      />
    );
  }

  const canReject = row.status === "pending" && product.status === "in_review";

  // An arrow function, so the narrowing of `row` above still holds inside it.
  const confirmReject = () => {
    rejectImage.mutate(
      { imageId: row.id, productId: product.id },
      { onSuccess: () => setIsRejectDialogOpen(false) },
    );
  };

  return (
    <Stack spacing={3} sx={{ maxWidth: 720 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
        <Chip
          size="small"
          color={STATUS_COLOR[row.status]}
          label={t(`admin.review.image.imageStatus.${row.status}`)}
        />
        <Box sx={{ flexGrow: 1 }} />
        {canReject && (
          <Button
            variant="outlined"
            color="error"
            startIcon={<Icon>hide_image</Icon>}
            onClick={() => {
              rejectImage.reset();
              setIsRejectDialogOpen(true);
            }}
          >
            {t("admin.review.image.reject")}
          </Button>
        )}
      </Stack>
      {row.status === "rejected" && (
        <Alert severity="info">{t("admin.review.image.rejectedNotice")}</Alert>
      )}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Box
          component="img"
          src={row.variants.detail}
          alt={product.name}
          loading="lazy"
          sx={{ width: "100%", height: "auto" }}
        />
      </Paper>
      <Stack direction="row" spacing={2}>
        {PREVIEW_VARIANTS.map((variant) => (
          <Box key={variant}>
            <Box
              component="img"
              src={row.variants[variant]}
              alt={product.name}
              loading="lazy"
              sx={{ maxHeight: 120 }}
            />
            <Typography variant="caption" display="block">
              {t(`admin.review.image.variant.${variant}`)}
            </Typography>
          </Box>
        ))}
      </Stack>
      <Box>
        <Typography variant="subtitle2">
          {t("admin.review.image.attributionHeading")}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {row.attribution ?? t("admin.review.image.attributionUnknown")}
        </Typography>
        <Link
          href={row.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          variant="body2"
        >
          {t("admin.review.image.sourceLink")}
        </Link>
      </Box>
      {isRejectDialogOpen && (
        <ConfirmDialog
          title={t("admin.review.image.rejectConfirmTitle")}
          body={t("admin.review.image.rejectConfirmBody")}
          confirmLabel={t("admin.review.image.reject")}
          confirmColor="error"
          isPending={rejectImage.isPending}
          hasError={rejectImage.isError}
          onConfirm={confirmReject}
          onClose={() => setIsRejectDialogOpen(false)}
        />
      )}
    </Stack>
  );
}
