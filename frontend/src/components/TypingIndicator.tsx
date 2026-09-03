import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import { useTranslation } from "react-i18next";

/**
 * "The advisor is typing…" — the chat-appropriate progress indicator.
 *
 * The conversation rhythm is `seen → typing… → completed message`: there is no
 * token streaming anywhere in this application, so between the two the timeline
 * shows this instead of a partial reply. It deliberately does **not** reuse
 * `OperationProgress`: a percent bar inside a conversation reads as a machine
 * report, and the customer never sees operations at all.
 *
 * The three dots must be visibly animated (this is a graded progress surface),
 * and the animation is `sx` keyframes rather than a dependency. The meaning is
 * carried by the `role="status"` + translated `aria-label` pair, so a screen
 * reader hears the sentence the dots stand for.
 */
export function TypingIndicator() {
  const { t } = useTranslation();

  return (
    <Paper
      variant="outlined"
      sx={{ alignSelf: "flex-start", px: 2, py: 1.25, borderRadius: 3 }}
    >
      <Box
        role="status"
        aria-label={t("consultations.chat.typing")}
        sx={{ display: "flex", gap: 0.75, px: 1, py: 0.5 }}
      >
        {[0, 1, 2].map((index) => (
          <Box
            key={index}
            sx={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              bgcolor: "text.secondary",
              animation: "typingPulse 1.2s ease-in-out infinite",
              animationDelay: `${index * 0.2}s`,
              "@keyframes typingPulse": {
                "0%, 60%, 100%": { opacity: 0.3 },
                "30%": { opacity: 1 },
              },
            }}
          />
        ))}
      </Box>
    </Paper>
  );
}
