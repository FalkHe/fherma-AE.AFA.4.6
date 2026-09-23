// The "Jump to the latest" pill (D12 §2, sprint 010/06 WI3 ← AC5).
// `Transcript.tsx` (WI2, built in parallel) owns placement -- it renders
// this only while scrolled up, inside its own sticky, centred wrapper --
// so this component is just the pill itself: label plus handler, nothing
// about where it sits.
import type { ReactElement } from "react";
import Button from "@mui/material/Button";
import { ArrowDown } from "lucide-react";
import { useTranslation } from "react-i18next";

export interface JumpToLatestPillProps {
  onClick: () => void;
}

export function JumpToLatestPill({ onClick }: JumpToLatestPillProps): ReactElement {
  const { t } = useTranslation("play");

  return (
    <Button
      variant="contained"
      size="small"
      onClick={onClick}
      startIcon={<ArrowDown size={16} aria-hidden />}
      sx={(theme) => ({
        borderRadius: theme.shape.borderRadiusPill,
        backgroundColor: "var(--surface-timber)",
        border: "1px solid var(--border-timber)",
        boxShadow: "var(--shadow-md)",
        color: theme.palette.text.primary,
        "&:hover": {
          backgroundColor: "var(--surface-timber)",
          boxShadow: "var(--shadow-lg)",
        },
      })}
    >
      {t("jumpToLatest")}
    </Button>
  );
}
