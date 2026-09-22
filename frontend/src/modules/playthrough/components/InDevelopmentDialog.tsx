// AC4 (docs/intents/007-initial-frontend, sprint 05): one reusable dialog
// for any feature that isn't built yet — "Be brave, this feature is in
// development". No copy props: every caller gets the same three strings
// from common:inDevelopment.*, so the message never drifts between call
// sites. Dialog/DialogTitle wire up aria-labelledby via MUI's own
// DialogContext (no manual id plumbing needed) and Escape/backdrop click
// both already call onClose through MUI's Modal.
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import { useTranslation } from "react-i18next";

export interface InDevelopmentDialogProps {
  open: boolean;
  onClose: () => void;
}

export function InDevelopmentDialog({ open, onClose }: InDevelopmentDialogProps) {
  const { t } = useTranslation("common");

  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>{t("inDevelopment.title")}</DialogTitle>
      <DialogContent>
        <DialogContentText>{t("inDevelopment.body")}</DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t("inDevelopment.close")}</Button>
      </DialogActions>
    </Dialog>
  );
}
