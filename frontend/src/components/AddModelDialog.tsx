import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ProductError, useCreateProduct } from "../hooks/useProducts";

/** Field errors this dialog can show, keyed by their translation key. */
type FieldErrorKey =
  | "admin.backlog.addDialog.nameRequired"
  | "admin.backlog.addDialog.duplicate";

/**
 * Adds a model to the backlog — the only way a motorcycle enters the
 * catalogue, and the trigger of the ingestion the backlog then shows progress
 * for (the submit label carries that side effect, which is why there is no
 * explanatory paragraph).
 *
 * Render it conditionally rather than toggling an `open` prop: mounting the
 * dialog per opening is what discards a half-typed name and a stale error
 * instead of showing them again next time.
 *
 * Server errors are mapped by status code alone (409 duplicate, 422
 * validation), never from the error text — the Phase-1 pattern.
 */
export function AddModelDialog({
  onClose,
  onCreated,
}: {
  /** Cancel, backdrop click or Escape — ignored while the mutation is pending. */
  onClose: () => void;
  /**
   * A model was created. The caller closes the dialog and clears its status
   * filter, so the new `backlog` row is visible right away.
   */
  onCreated: () => void;
}) {
  const { t } = useTranslation();
  const createProduct = useCreateProduct();

  const [name, setName] = useState("");
  const [fieldError, setFieldError] = useState<FieldErrorKey | null>(null);
  const [hasGeneralError, setHasGeneralError] = useState(false);

  const isPending = createProduct.isPending;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFieldError(null);
    setHasGeneralError(false);

    const trimmedName = name.trim();

    // Checked on submit only — no keystroke validation anywhere in this app.
    if (trimmedName === "") {
      setFieldError("admin.backlog.addDialog.nameRequired");
      return;
    }

    createProduct.mutate(
      { name: trimmedName },
      {
        onSuccess: () => {
          onCreated();
        },
        onError: (error) => {
          const status = error instanceof ProductError ? error.status : 0;

          if (status === 409) {
            setFieldError("admin.backlog.addDialog.duplicate");
            return;
          }

          if (status === 422) {
            // The request carries one field, so a validation error can only be
            // about the name.
            setFieldError("admin.backlog.addDialog.nameRequired");
            return;
          }

          // Network or 5xx: the typed value stays, so submitting again costs
          // one click.
          setHasGeneralError(true);
        },
      },
    );
  }

  return (
    <Dialog
      open
      // A dialog that vanishes mid-request would leave the admin guessing
      // whether the model was created.
      onClose={() => {
        if (!isPending) {
          onClose();
        }
      }}
      maxWidth="xs"
      fullWidth
    >
      <DialogTitle>{t("admin.backlog.addDialog.title")}</DialogTitle>
      <Box component="form" noValidate onSubmit={handleSubmit}>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {hasGeneralError && (
              <Alert severity="error">{t("common.errors.serverError")}</Alert>
            )}
            <TextField
              label={t("admin.backlog.addDialog.nameLabel")}
              helperText={
                fieldError === null
                  ? t("admin.backlog.addDialog.nameHint")
                  : t(fieldError)
              }
              error={fieldError !== null}
              name="name"
              autoFocus
              required
              fullWidth
              disabled={isPending}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} disabled={isPending}>
            {t("common.cancel")}
          </Button>
          <Button
            type="submit"
            variant="contained"
            disabled={isPending}
            startIcon={
              isPending ? <CircularProgress size={20} color="inherit" /> : undefined
            }
          >
            {t("admin.backlog.addDialog.submit")}
          </Button>
        </DialogActions>
      </Box>
    </Dialog>
  );
}
