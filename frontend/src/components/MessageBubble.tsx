import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Icon from "@mui/material/Icon";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

import type { ChatMessage } from "../hooks/useChatMessages";

import { MessageSources } from "./MessageSources";
import { RecommendationCard } from "./RecommendationCard";
import { ToolResultBlock } from "./ToolResultBlock";
import { UntrustedMarkdown } from "./UntrustedMarkdown";

/**
 * One message in the conversation: the user's own words on the right, the
 * advisor's answer on the left.
 *
 * The asymmetry is not only cosmetic. **User input is never rendered as
 * Markdown** — it is displayed as plain, pre-wrapped text, so nothing a user
 * types can style, link or otherwise dress itself up as advisor output. The
 * advisor's body goes through the shared `UntrustedMarkdown` renderer (GFM
 * tables, raw HTML **off** — never add `rehype-raw`), with links opening in a
 * new tab instead of navigating the SPA.
 *
 * The advisor's parts appear in one pinned order (ui-spec §6): what the advisor
 * *did* (tool blocks), the answer (Markdown body), the payoff (recommendation
 * cards), the receipts (sources toggle). This component owns that order;
 * each part owns its own rendering.
 *
 * It is a presentational component: it receives an already-fetched message and
 * translates only its own chrome. The send state arrives as a separate prop
 * because "seen" is a property of the *turn*, not of the message row (ui-spec
 * §3.3 derives it in the route from `activeOperationId`), while `sending` and
 * `failed` ride along on the optimistic entry itself.
 */

/**
 * Typography for the rendered answer, merged after `UntrustedMarkdown`'s base
 * sx: a wide table must scroll rather than push the bubble, and the first and
 * last block must not add margin inside the bubble's own padding. Palette
 * tokens only.
 */
const MARKDOWN_SX = {
  "& > :first-of-type": { mt: 0 },
  "& > :last-child": { mb: 0 },
  "& p": { my: 1 },
} as const;

/**
 * `maxWidth: "100%"` is load-bearing, not decoration: without it a wide
 * comparison table's min-content width pushes the whole bubble past the
 * viewport on a phone instead of scrolling inside it (ui-spec §8.3 — "the
 * bubble's maxWidth bounds it").
 */
const ASSISTANT_PAPER_SX = {
  px: 2,
  py: 1.25,
  borderRadius: 3,
  maxWidth: "100%",
} as const;

/**
 * Today's messages show the time, older ones the date as well — a conversation
 * is read as a sequence of turns, and a full date on every bubble is noise until
 * the turn is from another day.
 */
function formatTimestamp(createdAt: string, language: string): string {
  const timestamp = new Date(createdAt);
  const isToday = timestamp.toDateString() === new Date().toDateString();

  return isToday
    ? timestamp.toLocaleTimeString(language, { timeStyle: "short" })
    : timestamp.toLocaleString(language, {
        dateStyle: "medium",
        timeStyle: "short",
      });
}

export function MessageBubble({
  message,
  state,
  onRetry,
  onDiscard,
}: {
  message: ChatMessage;
  /**
   * Effective send state of a user message, resolved by the route: the
   * optimistic entry's own `state`, or `sent` on the newest user message while
   * the advisor's turn is in flight (that is the "Seen" signal).
   */
  state?: ChatMessage["state"];
  /** Re-fires the send with the same body; only for a failed message. */
  onRetry?: () => void;
  /** Drops the optimistic entry; only for a failed message. */
  onDiscard?: () => void;
}) {
  const { t, i18n } = useTranslation();

  const isUser = message.role === "user";
  const hasFailed = isUser && state === "failed";

  const paperSx = hasFailed
    ? {
        bgcolor: "transparent",
        border: 1,
        borderColor: "error.main",
        color: "text.primary",
        px: 2,
        py: 1.25,
        borderRadius: 3,
      }
    : {
        bgcolor: "primary.main",
        color: "primary.contrastText",
        px: 2,
        py: 1.25,
        borderRadius: 3,
      };

  function renderCaption() {
    if (isUser && state === "sending") {
      return (
        <>
          <CircularProgress size={12} color="inherit" />
          <Typography variant="caption">{t("consultations.chat.sending")}</Typography>
        </>
      );
    }

    if (isUser && state === "sent") {
      return (
        <>
          <Icon fontSize="inherit">check</Icon>
          <Typography variant="caption">{t("consultations.chat.seen")}</Typography>
        </>
      );
    }

    if (hasFailed) {
      // Colour is never the only signal: the error border is paired with the
      // words "Not sent." and with the two ways out of it.
      return (
        <>
          <Icon fontSize="inherit">error</Icon>
          <Typography variant="caption">{t("consultations.chat.sendFailed")}</Typography>
          {onRetry !== undefined && (
            <Button size="small" color="inherit" onClick={onRetry}>
              {t("consultations.chat.sendRetry")}
            </Button>
          )}
          {onDiscard !== undefined && (
            <Button size="small" color="inherit" onClick={onDiscard}>
              {t("consultations.chat.sendDiscard")}
            </Button>
          )}
        </>
      );
    }

    return (
      <Typography variant="caption">
        {formatTimestamp(message.createdAt, i18n.language)}
      </Typography>
    );
  }

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignSelf: isUser ? "flex-end" : "flex-start",
        alignItems: isUser ? "flex-end" : "flex-start",
        maxWidth: isUser ? { xs: "85%", sm: 560 } : { xs: "95%", sm: 720 },
      }}
    >
      {isUser ? (
        <Paper elevation={0} sx={paperSx}>
          <Typography
            variant="body1"
            sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
          >
            {message.body}
          </Typography>
        </Paper>
      ) : (
        <Paper variant="outlined" sx={ASSISTANT_PAPER_SX}>
          {/* What the advisor did — in call order, blocks and subtle rows mixed. */}
          {message.toolCalls.map((toolCall) => (
            <ToolResultBlock key={toolCall.id} toolCall={toolCall} />
          ))}
          <UntrustedMarkdown sx={MARKDOWN_SX}>{message.body}</UntrustedMarkdown>
          {message.recommendations.length > 0 && (
            <>
              <Typography variant="subtitle2" sx={{ mt: 1 }}>
                {t("consultations.recommendations.heading")}
              </Typography>
              <Stack
                direction={{ xs: "column", sm: "row" }}
                spacing={2}
                useFlexGap
                sx={{ flexWrap: "wrap", my: 1 }}
              >
                {message.recommendations.map((recommendation) => (
                  <RecommendationCard
                    key={recommendation.motorbikeId}
                    recommendation={recommendation}
                  />
                ))}
              </Stack>
            </>
          )}
          <MessageSources sources={message.sources} />
        </Paper>
      )}
      <Stack
        direction="row"
        spacing={0.5}
        sx={{
          alignItems: "center",
          mt: 0.25,
          color: hasFailed ? "error.main" : "text.secondary",
        }}
      >
        {renderCaption()}
      </Stack>
    </Box>
  );
}
