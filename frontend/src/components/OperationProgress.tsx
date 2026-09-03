import Button from "@mui/material/Button";
import Icon from "@mui/material/Icon";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { Operation } from "../hooks/useOperations";

/**
 * Live state of one background operation — this project's progress indicator
 * for long operations.
 *
 * It renders whatever the operation row currently says and nothing else: no
 * timers, no interpolation, no polling. Freshness comes from the SSE listener
 * invalidating `["operations"]`, which refetches the row and re-renders this
 * component; the same element is used in the backlog's progress cell and on the
 * review page's ingesting gate, so both show one progressbar semantic.
 *
 * The `message` is server-generated English (`Fetching sources (2/6)`) and is
 * rendered verbatim — the pinned exemption from i18n, like document prose.
 */
export function OperationProgress({
  operation,
  name,
  onRetry,
}: {
  operation: Pick<Operation, "status" | "progress" | "message">;
  /** Model display name, for the progressbar's accessible label. */
  name: string;
  /** Renders a retry control on a failed operation when supplied. */
  onRetry?: () => void;
}) {
  const { t } = useTranslation();
  const { status, progress, message } = operation;

  // A finished operation has nothing to report: the model's status chip is the
  // signal, and an empty cell keeps the table quiet.
  if (status === "succeeded") {
    return null;
  }

  // Suffix rather than a separate line: "40% — Fetching sources (2/6)" reads as
  // one sentence and keeps the table cell to two rows.
  const messageSuffix = message === null ? "" : ` — ${message}`;
  const progressLabel = t("admin.backlog.progressLabel", { name });

  if (status === "failed") {
    return (
      <Stack spacing={0.5}>
        <Typography variant="caption" color="error">
          {t("admin.backlog.ingestionFailed")}
          {messageSuffix}
        </Typography>
        {onRetry !== undefined && (
          <Button
            size="small"
            startIcon={<Icon>refresh</Icon>}
            onClick={onRetry}
            sx={{ alignSelf: "flex-start" }}
          >
            {t("admin.backlog.retryIngestion")}
          </Button>
        )}
      </Stack>
    );
  }

  if (status === "queued") {
    return (
      <Stack spacing={0.5}>
        <LinearProgress variant="indeterminate" aria-label={progressLabel} />
        <Typography variant="caption" color="text.secondary">
          {t("admin.backlog.operationQueued")}
        </Typography>
      </Stack>
    );
  }

  return (
    <Stack spacing={0.5}>
      <LinearProgress
        variant="determinate"
        value={progress}
        aria-label={progressLabel}
      />
      <Typography variant="caption" color="text.secondary">
        {t("admin.backlog.percentComplete", { value: progress })}
        {messageSuffix}
      </Typography>
    </Stack>
  );
}
