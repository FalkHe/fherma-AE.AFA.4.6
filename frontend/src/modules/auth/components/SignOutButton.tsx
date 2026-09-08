// Presentational only: it holds no hook of its own. HomeRoute owns the
// single `useSignOut()` instance and passes its state in as props
// (step-0.1.md §6.3.1, ui-spec.md §3.3).
import Button from "@mui/material/Button";
import { useTranslation } from "react-i18next";

export interface SignOutButtonProps {
  onClick: () => void;
  loading: boolean;
}

export function SignOutButton({ onClick, loading }: SignOutButtonProps) {
  const { t } = useTranslation("auth");

  return (
    <Button color="inherit" loading={loading} onClick={onClick}>
      {t("signOut.action")}
    </Button>
  );
}
