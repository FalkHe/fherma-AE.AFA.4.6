// The play screen's composer (sprint 010/07 WI1 ← AC1, I1). Open state is a
// real `<form>` -- text field plus Send, submitting on Enter or the button,
// same shape as the character module's `Composer` (`frontend/src/modules/
// character/components/Composer.tsx`). The three closed states never
// render the field at all: each is one in-voice line, styled like
// `SystemLine` (centred, muted, no interactive control), because a running
// turn, a pending question or a pending roll each already say what is
// happening -- nothing here is clickable while one of them holds the floor.
import { type FormEvent, type ReactElement, useState } from "react";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useTranslation } from "react-i18next";

export type ComposerState = "open" | "turnRunning" | "awaitingChoice" | "awaitingRoll";

export interface ComposerProps {
  state: ComposerState;
  onSend: (text: string) => void;
}

export function Composer({ state, onSend }: ComposerProps): ReactElement {
  const { t } = useTranslation("play");
  const [text, setText] = useState("");

  if (state !== "open") {
    let line: string;
    switch (state) {
      case "turnRunning":
        line = t("composer.turnRunning");
        break;
      case "awaitingChoice":
        line = t("composer.awaitingChoice");
        break;
      case "awaitingRoll":
        line = t("composer.awaitingRoll");
        break;
    }

    return (
      <Typography
        sx={{
          color: "text.secondary",
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-small)",
          textAlign: "center",
        }}
      >
        {line}
      </Typography>
    );
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = text.trim();
    if (trimmed === "") {
      return;
    }
    onSend(trimmed);
    setText("");
  }

  return (
    <Stack direction="row" spacing={2} component="form" onSubmit={handleSubmit}>
      <TextField
        id="play-composer"
        name="message"
        label={t("composer.placeholder")}
        fullWidth
        value={text}
        onChange={(event) => setText(event.target.value)}
        autoComplete="off"
      />
      <Button type="submit" variant="contained">
        {t("composer.send")}
      </Button>
    </Stack>
  );
}
