// The free-text input row (sprint 009-06, WI1, AC2) — a real `<form>` that
// submits on Enter and clears itself once its text is handed off, matching
// `SignInForm`'s form/TextField/Button shape (frontend-stack.md
// "Accessibility baseline").
//
// Creation-chat viewport fix: while a message is in flight (`disabled`) the
// field turns read-only rather than disabled, so focus stays in it (a
// disabled input drops focus); only the Send button is disabled, and a
// submit (Enter) meanwhile does nothing.
import { type FormEvent, useState } from "react";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { useTranslation } from "react-i18next";

export interface ComposerProps {
  onSend: (text: string) => void;
  disabled: boolean;
}

export function Composer({ onSend, disabled }: ComposerProps) {
  const { t } = useTranslation("character");
  const [text, setText] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (disabled) {
      return;
    }
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
        id="creation-chat-composer"
        name="message"
        label={t("chat.placeholder")}
        fullWidth
        value={text}
        onChange={(event) => setText(event.target.value)}
        slotProps={{ input: { readOnly: disabled } }}
        autoComplete="off"
      />
      <Button type="submit" variant="contained" disabled={disabled}>
        {t("chat.send")}
      </Button>
    </Stack>
  );
}
