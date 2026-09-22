// The confirmation before an in-app exit (sprint 009-06, WI1, AC4, D16) —
// same shape as `playthrough`'s `InDevelopmentDialog`, wired to this page's
// own two outcomes instead of a single dismiss.
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import { useTranslation } from "react-i18next";

export interface LeaveDialogProps {
  open: boolean;
  onStay: () => void;
  onLeave: () => void;
}

export function LeaveDialog({ open, onStay, onLeave }: LeaveDialogProps) {
  const { t } = useTranslation("character");

  return (
    <Dialog open={open} onClose={onStay}>
      <DialogTitle>{t("leave.title")}</DialogTitle>
      <DialogContent>
        <DialogContentText>{t("leave.body")}</DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onStay}>{t("leave.stay")}</Button>
        <Button onClick={onLeave} color="error">
          {t("leave.leave")}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
