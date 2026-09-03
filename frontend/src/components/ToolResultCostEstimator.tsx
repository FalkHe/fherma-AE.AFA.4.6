import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Icon from "@mui/material/Icon";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { CostEstimatorResult } from "./toolResults";
import { isUsedPrice } from "./usedPrice";
import { UsedPriceSnapshot } from "./UsedPriceSnapshot";

/**
 * What owning the bike costs (ui-spec §8.5).
 *
 * Every number here is modelled, not quoted, so the disclosure is **always
 * visible**: the "Estimate" chip sits in the block header (never behind a
 * toggle) and the assumption *count* is on screen even while the list itself is
 * collapsed. Line-item labels — including any "/year" qualifier — are
 * server-composed English and rendered verbatim.
 */

/** The always-visible "this is modelled, not quoted" disclosure (header slot). */
export function CostEstimateChip() {
  const { t } = useTranslation();

  return (
    <Chip
      size="small"
      variant="outlined"
      color="warning"
      label={t("consultations.tools.costEstimator.estimate")}
    />
  );
}

export function ToolResultCostEstimator({ result }: { result: CostEstimatorResult }) {
  const { t, i18n } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  // Whole euros: the precision of an estimate is not in its cents.
  const money = new Intl.NumberFormat(i18n.language, {
    style: "currency",
    currency: result.currency,
    maximumFractionDigits: 0,
  });

  return (
    <>
      <Table size="small">
        <TableBody>
          {result.lineItems.map((item) => (
            <TableRow key={item.label}>
              <TableCell component="th" scope="row" sx={{ borderBottom: 0, py: 0.25 }}>
                {item.label}
              </TableCell>
              <TableCell align="right" sx={{ borderBottom: 0, py: 0.25 }}>
                {money.format(item.amount)}
              </TableCell>
            </TableRow>
          ))}
          <TableRow>
            <TableCell
              component="th"
              scope="row"
              sx={{ fontWeight: "bold", py: 0.25, borderBottom: 0 }}
            >
              {t("consultations.tools.costEstimator.total")}
            </TableCell>
            <TableCell
              align="right"
              sx={{ fontWeight: "bold", py: 0.25, borderBottom: 0 }}
            >
              {money.format(result.total)}
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
      {result.assumptions.length > 0 && (
        <>
          <Button
            size="small"
            color="inherit"
            onClick={() => setExpanded((open) => !open)}
            aria-expanded={expanded}
            startIcon={
              <Icon
                sx={{
                  transform: expanded ? "rotate(180deg)" : "none",
                  transition: "transform 150ms",
                }}
              >
                expand_more
              </Icon>
            }
          >
            {t("consultations.tools.costEstimator.assumptions", {
              count: result.assumptions.length,
            })}
          </Button>
          <Collapse in={expanded}>
            <List dense disablePadding>
              {result.assumptions.map((assumption) => (
                <ListItem key={assumption} disableGutters sx={{ py: 0 }}>
                  <ListItemText
                    primary={assumption}
                    slotProps={{ primary: { variant: "caption" } }}
                  />
                </ListItem>
              ))}
            </List>
          </Collapse>
        </>
      )}
      {isUsedPrice(result.usedPrice) && (
        <>
          <Divider sx={{ my: 1 }} />
          <UsedPriceSnapshot usedPrice={result.usedPrice} currency={result.currency} />
        </>
      )}
    </>
  );
}
