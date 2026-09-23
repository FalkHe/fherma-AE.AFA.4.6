// A grid of labelled stat cells — a caption `dt` above a big `dd` value, on
// the inset surface (creation-chat viewport fix). Shared by `SheetPanel`
// (abilities, hit points/armour class, compact) and `ReviewPanel` (vitals and
// abilities, roomy, abilities with a modifier line). A cell's modifier is a
// second `dd` under the same `dt`, so a screen reader reads "STR, 8, −1"
// rather than one run-together "8−1".
//
// `component` is `"div"` when the caller already owns the surrounding `<dl>`
// (`SheetPanel`'s one field list) and `"dl"` when this grid is the list.
import type { ReactElement } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

export interface StatCell {
  label: string;
  value: string;
  modifier?: { text: string; negative: boolean };
}

/** A `gridTemplateColumns` value, plain or per breakpoint. */
type Columns = string | Partial<Record<"xs" | "sm" | "md" | "lg" | "xl", string>>;

export interface StatCellsProps {
  rows: StatCell[];
  columns: Columns;
  mono?: boolean;
  size?: "compact" | "roomy";
  component?: "div" | "dl";
}

export function StatCells({
  rows,
  columns,
  mono = false,
  size = "compact",
  component = "div",
}: StatCellsProps): ReactElement {
  const roomy = size === "roomy";

  return (
    <Box component={component} sx={{ display: "grid", gridTemplateColumns: columns, gap: 3, m: 0 }}>
      {rows.map((row) => (
        <Box
          key={row.label}
          sx={{
            bgcolor: "var(--surface-inset)",
            border: "1px solid var(--border-hairline)",
            borderRadius: "var(--radius-md)",
            py: roomy ? 4 : 2,
            textAlign: "center",
          }}
        >
          <Typography component="dt" variant="caption" sx={{ display: "block", color: "text.disabled" }}>
            {row.label}
          </Typography>
          <Typography
            component="dd"
            sx={{
              m: 0,
              fontFamily: mono ? "var(--font-mono)" : "var(--font-display)",
              fontWeight: "var(--weight-bold)",
              fontSize: roomy ? "1.5rem" : "1.25rem",
            }}
          >
            {row.value}
          </Typography>
          {row.modifier && (
            <Typography
              component="dd"
              sx={{
                m: 0,
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: row.modifier.negative ? "var(--ember-400)" : "var(--moss-300)",
              }}
            >
              {row.modifier.text}
            </Typography>
          )}
        </Box>
      ))}
    </Box>
  );
}
