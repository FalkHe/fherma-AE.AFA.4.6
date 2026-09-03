import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Icon from "@mui/material/Icon";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { ProductSuggestion } from "../hooks/useProductReview";

/**
 * The unverified-claim block (roadmap 6.3, ui-spec §2, shared-knowledge D6).
 *
 * **Component boundary, stated once (ui-spec §2.1 "enforced twice"):** this
 * module is the *only* place `frontend/src/` accepts claim
 * (`ProductSuggestion`) data. Its only importer is `ModelIdentityPanel.tsx`,
 * whose only importer is `AdminModelReviewRoute.tsx` (rendered under
 * `RequireAdmin`). No component that a customer route imports may accept a
 * `suggestion`/claim prop — the compile-time half of the boundary lives in
 * `useCatalogueModels`/`useCatalogueModel`, whose customer types simply have
 * no such member.
 *
 * "Use the claim" only ever fills the identity **form buffer** — it never
 * saves. A claimed value becomes catalogue data exactly when the admin saves
 * it into the typed columns and later approves, i.e. through the same path a
 * typed value takes, never by rendering the claim itself.
 */

/** `admin.identity.claim.*` — the box at the top of the Identity tab (§2.2). */
export function ModelClaimPanel({
  suggestion,
  collapsed = false,
}: {
  suggestion: ProductSuggestion;
  /** Approved rows (§1.7) render this collapsed — history, not a task. */
  collapsed?: boolean;
}) {
  const { t } = useTranslation();

  const chip = (
    <Chip
      size="small"
      color="warning"
      variant="outlined"
      icon={<Icon>flag</Icon>}
      label={t("admin.identity.claim.heading")}
    />
  );

  const body = (
    <Stack spacing={1}>
      {!collapsed && (
        <>
          {chip}
          <Typography variant="caption" color="text.secondary">
            {t("admin.identity.claim.hint")}
          </Typography>
        </>
      )}
      <Stack direction="row" spacing={1}>
        <Typography variant="body2" fontWeight={600}>
          {t("admin.identity.claim.listedAs")}
        </Typography>
        {/* Verbatim, file-derived text — plain Typography, never markdown. */}
        <Typography variant="body2">&quot;{suggestion.raw}&quot;</Typography>
      </Stack>
      <Stack direction="row" spacing={1}>
        <Typography variant="body2" fontWeight={600}>
          {t("admin.identity.claim.source")}
        </Typography>
        <Typography variant="body2">{suggestion.source}</Typography>
      </Stack>
      {suggestion.links.length > 0 && (
        <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
          <Typography variant="body2" fontWeight={600}>
            {t("admin.identity.claim.links")}
          </Typography>
          {suggestion.links.map((url) => (
            <Link
              key={url}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              sx={{ wordBreak: "break-word" }}
            >
              {url}
            </Link>
          ))}
        </Stack>
      )}
    </Stack>
  );

  if (collapsed) {
    return (
      <Accordion variant="outlined">
        <AccordionSummary expandIcon={<Icon>expand_more</Icon>}>{chip}</AccordionSummary>
        <AccordionDetails>{body}</AccordionDetails>
      </Accordion>
    );
  }

  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
      {body}
    </Paper>
  );
}

/**
 * A single per-field claim row (ui-spec §2.3), rendered by `ModelIdentityPanel`
 * directly under the identity form field it corresponds to. Kept in this
 * module (not `ModelIdentityPanel.tsx`) so every renderer of claim content —
 * including this smaller row — stays behind the one component boundary
 * described above.
 */
export function ClaimFieldRow({
  value,
  useLabel,
  useA11yLabel,
  disabled = false,
  onUse,
  noMatchCaption,
}: {
  /** The claimed value, already formatted for display. */
  value: string;
  useLabel: string;
  useA11yLabel: string;
  disabled?: boolean;
  /**
   * Fills the form buffer. `undefined` renders `noMatchCaption` instead of a
   * button — the manufacturer row when no curated option matches (§2.3).
   */
  onUse?: () => void;
  noMatchCaption?: string;
}) {
  const { t } = useTranslation();

  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
      <Typography variant="caption" color="text.secondary">
        {t("admin.identity.claim.value", { value })}
      </Typography>
      {onUse !== undefined ? (
        <Button
          size="small"
          variant="text"
          disabled={disabled}
          onClick={onUse}
          aria-label={useA11yLabel}
        >
          {useLabel}
        </Button>
      ) : (
        noMatchCaption !== undefined && (
          <Typography variant="caption" color="text.secondary">
            {noMatchCaption}
          </Typography>
        )
      )}
    </Stack>
  );
}
