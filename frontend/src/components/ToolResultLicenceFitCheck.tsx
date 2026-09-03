import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { LicenceFitCheckResult, LicenceVerdict } from "./toolResults";

/**
 * Whether a bike is legal and physically fits the rider (ui-spec §8.4).
 *
 * The evidence line is the point of this block: a verdict without the numbers
 * behind it is an opinion. `label` and `evidence` are server-composed English
 * strings and are rendered **verbatim** (the same i18n exemption as operation
 * messages) — only the verdict itself is translated, and the chip carries that
 * word next to its colour, because colour is never the only signal.
 */

const VERDICT_COLOR = {
  pass: "success",
  fail: "error",
  unknown: "default",
} as const satisfies Record<LicenceVerdict, "success" | "error" | "default">;

export function ToolResultLicenceFitCheck({ result }: { result: LicenceFitCheckResult }) {
  const { t } = useTranslation();

  return (
    <Stack spacing={1}>
      {result.rules.map((rule) => (
        <Stack
          key={rule.rule}
          direction="row"
          spacing={1}
          sx={{ alignItems: "flex-start" }}
        >
          <Chip
            size="small"
            color={VERDICT_COLOR[rule.verdict]}
            label={t(`consultations.tools.licenceFitCheck.verdict.${rule.verdict}`)}
          />
          <Box>
            <Typography variant="body2">{rule.label}</Typography>
            {rule.evidence !== null && rule.evidence !== undefined && (
              <Typography variant="caption" color="text.secondary">
                {rule.evidence}
              </Typography>
            )}
          </Box>
        </Stack>
      ))}
    </Stack>
  );
}
