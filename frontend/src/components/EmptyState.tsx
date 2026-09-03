import Icon from "@mui/material/Icon";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

/**
 * The application's empty/error placeholder, extracted from the Phase-1
 * pattern now that four screens need it: centred stack, 56px Material Symbols
 * glyph in `text.secondary`, `h6` title, `body2` body capped near 440px and an
 * optional action last.
 *
 * Strings arrive already translated — the component is used for empty lists,
 * filtered-away lists, load failures and 404s, so it has no business guessing
 * which key belongs to which situation.
 */
export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  /** Material Symbols ligature, e.g. `two_wheeler`. */
  icon: string;
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <Stack
      spacing={1}
      alignItems="center"
      sx={{ py: 8, textAlign: "center", color: "text.secondary" }}
    >
      <Icon sx={{ fontSize: 56 }}>{icon}</Icon>
      <Typography variant="h6" component="h2" color="text.primary">
        {title}
      </Typography>
      <Typography variant="body2" sx={{ maxWidth: 440 }}>
        {body}
      </Typography>
      {action !== undefined && <Stack sx={{ pt: 2 }}>{action}</Stack>}
    </Stack>
  );
}
