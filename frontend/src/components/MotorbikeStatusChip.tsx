import Chip, { type ChipProps } from "@mui/material/Chip";
import { useTranslation } from "react-i18next";

import type { ProductStatus } from "../hooks/useProducts";

/**
 * Status of a catalogue model as a filled MUI chip.
 *
 * It exists so the colour/label mapping lives in exactly one place — the same
 * status is shown in the backlog table, the review header and (later) the
 * catalogue, and three hand-written mappings would drift apart.
 *
 * Colour is never the only signal: every chip carries its translated label.
 */
const STATUS_COLOR: Record<ProductStatus, ChipProps["color"]> = {
  backlog: "default",
  ingesting: "info",
  in_review: "warning",
  approved: "success",
  rejected: "error",
};

export function MotorbikeStatusChip({ status }: { status: ProductStatus }) {
  const { t } = useTranslation();

  return (
    <Chip
      size="small"
      // A status added by a later backend version is not in the map and in no
      // catalogue: it renders neutral with its raw value rather than crashing
      // the row or showing a bare key.
      color={STATUS_COLOR[status] ?? "default"}
      label={t(`admin.status.${status}`, { defaultValue: status })}
    />
  );
}
