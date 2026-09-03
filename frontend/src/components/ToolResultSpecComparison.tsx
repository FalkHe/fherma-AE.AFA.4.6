import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import { useTranslation } from "react-i18next";

import { formatSpecValue, specFieldLabel, specFieldUnit } from "./specFields";
import type { SpecComparisonResult } from "./toolResults";

/**
 * The in-chat spec comparison (ui-spec §8.3).
 *
 * The table never wraps and never drops a column: on a narrow viewport it
 * **scrolls horizontally inside the bubble**, because a comparison with a
 * hidden column is a comparison that lies. An unverified value renders as an
 * em dash carrying `common.unknown` — never blank, never a guess.
 */

/** Enough width per column that names and numbers stay on one line. */
const COLUMN_WIDTH = 120;

export function ToolResultSpecComparison({ result }: { result: SpecComparisonResult }) {
  const { t } = useTranslation();

  return (
    <TableContainer sx={{ overflowX: "auto" }}>
      <Table
        size="small"
        sx={{ minWidth: COLUMN_WIDTH * (result.bikes.length + 1) }}
        aria-label={t("consultations.tools.specComparison.tableLabel")}
      >
        <TableHead>
          <TableRow>
            <TableCell>{t("consultations.tools.specComparison.attribute")}</TableCell>
            {result.bikes.map((bike) => (
              <TableCell key={bike.motorbikeId} sx={{ whiteSpace: "nowrap" }}>
                {bike.name}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {result.rows.map((row) => {
            const unit = specFieldUnit(t, row.field);
            const label = specFieldLabel(t, row.field);

            return (
              <TableRow key={row.field}>
                <TableCell component="th" scope="row" sx={{ whiteSpace: "nowrap" }}>
                  {unit === "" ? label : `${label} (${unit})`}
                </TableCell>
                {result.bikes.map((bike, index) => {
                  const value = formatSpecValue(t, row.values[index]);

                  return value === null ? (
                    <TableCell key={bike.motorbikeId} aria-label={t("common.unknown")}>
                      —
                    </TableCell>
                  ) : (
                    <TableCell key={bike.motorbikeId}>{value}</TableCell>
                  );
                })}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
