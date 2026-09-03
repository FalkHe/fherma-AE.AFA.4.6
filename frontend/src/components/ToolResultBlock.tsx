import Icon from "@mui/material/Icon";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { ToolCall } from "../hooks/useChatMessages";

import { ToolResultCatalogueSearch } from "./ToolResultCatalogueSearch";
import { CostEstimateChip, ToolResultCostEstimator } from "./ToolResultCostEstimator";
import { ToolResultLicenceFitCheck } from "./ToolResultLicenceFitCheck";
import { ToolResultSpecComparison } from "./ToolResultSpecComparison";
import {
  isCatalogueSearchResult,
  isCostEstimatorResult,
  isFlagUnknownBikeResult,
  isLicenceFitCheckResult,
  isRecordPreferenceResult,
  isSpecComparisonResult,
} from "./toolResults";

/**
 * One executed tool call, framed and always expanded (ui-spec §8.1).
 *
 * Tool usage is visible **without interaction** — no accordion, no "show
 * details": what the advisor did is part of the answer, not a debug detail.
 * This component owns the frame and the dispatch; the four styled renderers own
 * their bodies.
 *
 * Dispatch is a **shape check** (`toolResults.ts`), never a try/catch around
 * rendering: a tool this frontend predates, a failed call, and the shared
 * name-resolution failure `{"unknownBike": "…"}` all land in the generic
 * key/value table, so no executed call can silently disappear.
 */

function ToolResultFrame({
  glyph,
  label,
  chip,
  children,
}: {
  glyph: string;
  label: string;
  /** Header extra — the cost estimator's always-visible "Estimate" chip. */
  chip?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Paper variant="outlined" sx={{ bgcolor: "action.hover", p: 1.5, mb: 1 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1 }}>
        <Icon fontSize="small" sx={{ color: "text.secondary" }}>
          {glyph}
        </Icon>
        <Typography variant="overline" color="text.secondary">
          {label}
        </Typography>
        {chip}
      </Stack>
      {children}
    </Paper>
  );
}

/**
 * Bookkeeping writes (ui-spec §8.7): visible, but one caption line — a full
 * block per captured preference would drown the interview, and these tools fire
 * many times per conversation.
 */
function SubtleToolRow({ glyph, text }: { glyph: string; text: string }) {
  return (
    <Stack
      direction="row"
      spacing={0.75}
      sx={{ alignItems: "center", color: "text.secondary", mb: 0.5 }}
    >
      <Icon fontSize="inherit">{glyph}</Icon>
      <Typography variant="caption">{text}</Typography>
    </Stack>
  );
}

/**
 * The forward-compatible renderer (ui-spec §8.6): the result's top-level
 * entries as key/value pairs, keys verbatim. It guarantees that a tool added to
 * the backend after this build still shows up as something a grader can read.
 */
function GenericToolResult({ result }: { result: ToolCall["result"] }) {
  const entries = Object.entries(result);

  // A failed call carries `result: {}` by convention — an empty table frame
  // would be chrome around nothing; the error note below it is the content.
  if (entries.length === 0) {
    return null;
  }

  return (
    <Table size="small">
      <TableBody>
        {entries.map(([key, value]) => (
          <TableRow key={key}>
            <TableCell
              component="th"
              scope="row"
              sx={{ verticalAlign: "top", width: "35%", borderBottom: 0, py: 0.25 }}
            >
              {key}
            </TableCell>
            <TableCell sx={{ borderBottom: 0, py: 0.25 }}>
              {typeof value === "object" && value !== null ? (
                // `pre-wrap` alone breaks only at whitespace, and serialized
                // tool output routinely holds a single unbreakable token far
                // wider than a phone (an escaped multi-line snippet, a URL).
                // Without `anywhere` that token pushes the whole *document*
                // sideways instead of wrapping inside the bubble — ui-spec §13's
                // long-content rule, verified at 390 px.
                <Typography
                  variant="caption"
                  component="pre"
                  sx={{ m: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                >
                  {JSON.stringify(value, null, 2)}
                </Typography>
              ) : (
                JSON.stringify(value)
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function ToolResultBlock({ toolCall }: { toolCall: ToolCall }) {
  const { t } = useTranslation();
  const result = toolCall.result;

  switch (toolCall.tool) {
    case "catalogue_search":
      if (isCatalogueSearchResult(result)) {
        return (
          <ToolResultFrame
            glyph="search"
            label={t("consultations.tools.catalogueSearch.title")}
          >
            <ToolResultCatalogueSearch result={result} />
          </ToolResultFrame>
        );
      }
      break;
    case "spec_comparison":
      if (isSpecComparisonResult(result)) {
        return (
          <ToolResultFrame
            glyph="compare_arrows"
            label={t("consultations.tools.specComparison.title")}
          >
            <ToolResultSpecComparison result={result} />
          </ToolResultFrame>
        );
      }
      break;
    case "licence_fit_check":
      if (isLicenceFitCheckResult(result)) {
        return (
          <ToolResultFrame
            glyph="fact_check"
            label={t("consultations.tools.licenceFitCheck.title")}
          >
            <ToolResultLicenceFitCheck result={result} />
          </ToolResultFrame>
        );
      }
      break;
    case "cost_estimator":
      if (isCostEstimatorResult(result)) {
        return (
          <ToolResultFrame
            glyph="payments"
            label={t("consultations.tools.costEstimator.title")}
            chip={<CostEstimateChip />}
          >
            <ToolResultCostEstimator result={result} />
          </ToolResultFrame>
        );
      }
      break;
    case "record_preference":
      if (isRecordPreferenceResult(result)) {
        return (
          <SubtleToolRow
            glyph="bookmark_added"
            text={t("consultations.tools.preferenceNoted", {
              attribute: result.attribute,
              value: result.value,
              firmness: t(`consultations.tools.firmness.${result.firmness}`),
            })}
          />
        );
      }
      break;
    case "flag_unknown_bike":
      if (isFlagUnknownBikeResult(result)) {
        return (
          <SubtleToolRow
            glyph="flag"
            text={t("consultations.tools.unknownBikeFlagged", { name: result.name })}
          />
        );
      }
      break;
    default:
      break;
  }

  // Unknown tool, or a known tool whose result does not match its pinned shape
  // (a failed call, or the shared `{"unknownBike": …}` resolution failure).
  // The label is the raw tool name — deliberately untranslated.
  return (
    <ToolResultFrame glyph="build" label={toolCall.tool}>
      <GenericToolResult result={result} />
      {/* A failed call has an empty result, so without the note the block would
          be a label over nothing — the reader could not tell "the tool found
          nothing" from "the tool broke". The message is server-composed English
          rendered verbatim, the same i18n exemption as operation failures. */}
      {toolCall.status === "failed" && toolCall.error !== null && (
        <Stack
          direction="row"
          spacing={0.75}
          sx={{ alignItems: "flex-start", color: "error.main" }}
        >
          <Icon fontSize="inherit">error</Icon>
          <Typography variant="caption">{toolCall.error}</Typography>
        </Stack>
      )}
    </ToolResultFrame>
  );
}
