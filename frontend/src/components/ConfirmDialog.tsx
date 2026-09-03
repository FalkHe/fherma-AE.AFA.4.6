import Alert from "@mui/material/Alert";
import Button, { type ButtonProps } from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import { useTranslation } from "react-i18next";

/**
 * The admin UI's confirmation step, used by all three irreversible-ish review
 * actions (approve model, reject model, reject image).
 *
 * Strings arrive already translated, as in `EmptyState` — the dialog is reused
 * for three different decisions and has no business guessing which key belongs
 * to which. The one exception is the failure notice: which key that is follows
 * from the dialog itself, not from the caller.
 *
 * Render it conditionally rather than toggling an `open` prop (the landed
 * `AddModelDialog` convention): mounting per opening is what discards a stale
 * error state.
 */
export function ConfirmDialog({
  title,
  body,
  warning,
  confirmLabel,
  confirmColor = "primary",
  isPending = false,
  hasError = false,
  errorMessage,
  onConfirm,
  onClose,
}: {
  title: string;
  body: string;
  /**
   * Second paragraph in `warning.main`, e.g. the unsaved-spec-edits notice on
   * the approve dialog.
   */
  warning?: string;
  confirmLabel: string;
  confirmColor?: ButtonProps["color"];
  /** While true the dialog cannot be dismissed and both buttons are disabled. */
  isPending?: boolean;
  /** The mutation failed; the dialog stays open and says so. */
  hasError?: boolean;
  /**
   * A specific failure message, replacing the generic "action failed" text
   * when `hasError` is true — e.g. the approve dialog's `incomplete-identity`
   * explanation (ui-spec §1.6). Absent renders exactly today's generic text,
   * so every other call site is unchanged.
   */
  errorMessage?: string;
  onConfirm: () => void;
  /** Cancel, backdrop click or Escape — ignored while the mutation is pending. */
  onClose: () => void;
}) {
  const { t } = useTranslation();

  return (
    <Dialog
      open
      // A dialog that vanishes mid-request would leave the admin guessing
      // whether the action went through.
      onClose={() => {
        if (!isPending) {
          onClose();
        }
      }}
      maxWidth="xs"
      fullWidth
    >
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        {hasError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {errorMessage ?? t("admin.review.actions.actionError")}
          </Alert>
        )}
        <DialogContentText>{body}</DialogContentText>
        {warning !== undefined && (
          <DialogContentText sx={{ color: "warning.main", mt: 1 }}>
            {warning}
          </DialogContentText>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={isPending}>
          {t("common.cancel")}
        </Button>
        <Button
          variant="contained"
          color={confirmColor}
          onClick={onConfirm}
          disabled={isPending}
          startIcon={
            isPending ? <CircularProgress size={20} color="inherit" /> : undefined
          }
        >
          {confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
