// ui-spec.md §3.1, §4, §5, §6.1. Sign-in validates presence only — length
// and charset rules are deliberately not applied here (they would leak
// account-format information to an attacker).
import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { useTranslation } from "react-i18next";

import type { ApiFailure } from "../../../core/api/errors";
import { useSignIn } from "../hooks/useSignIn";
import {
  USERNAME_MAX,
  translateFieldError,
  validatePasswordRequired,
  validateUsernameRequired,
  type FieldValidationError,
} from "../validation";

export interface SignInFormProps {
  sessionExpired: boolean;
}

export function SignInForm({ sessionExpired }: SignInFormProps) {
  const { t } = useTranslation("auth");
  const { t: tCommon } = useTranslation("common");
  const mutation = useSignIn();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [usernameEdited, setUsernameEdited] = useState(false);
  const [passwordEdited, setPasswordEdited] = useState(false);
  const [usernameError, setUsernameError] = useState<FieldValidationError | null>(null);
  const [passwordError, setPasswordError] = useState<FieldValidationError | null>(null);

  const usernameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);

  // Focus the session-expired notice once, on mount only — never re-run.
  useEffect(() => {
    if (sessionExpired) {
      alertRef.current?.focus();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Focus a fresh submit failure so a keyboard user lands next to it (UI-11).
  useEffect(() => {
    if (mutation.error) {
      alertRef.current?.focus();
    }
  }, [mutation.error]);

  function handleUsernameChange(event: ChangeEvent<HTMLInputElement>) {
    setUsername(event.target.value);
    setUsernameEdited(true);
    setUsernameError(null);
    if (mutation.isError) {
      mutation.reset();
    }
  }

  function handlePasswordChange(event: ChangeEvent<HTMLInputElement>) {
    setPassword(event.target.value);
    setPasswordEdited(true);
    setPasswordError(null);
    if (mutation.isError) {
      mutation.reset();
    }
  }

  function handleUsernameBlur() {
    if (usernameEdited) {
      setUsernameError(validateUsernameRequired(username));
    }
  }

  function handlePasswordBlur() {
    if (passwordEdited) {
      setPasswordError(validatePasswordRequired(password));
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();

    const nextUsernameError = validateUsernameRequired(username);
    const nextPasswordError = validatePasswordRequired(password);
    setUsernameError(nextUsernameError);
    setPasswordError(nextPasswordError);
    setUsernameEdited(true);
    setPasswordEdited(true);

    if (nextUsernameError) {
      usernameRef.current?.focus();
      return;
    }
    if (nextPasswordError) {
      passwordRef.current?.focus();
      return;
    }

    mutation.mutate(
      { username: username.trim(), password },
      {
        onError: (error: ApiFailure) => {
          if (error.code === "INVALID_CREDENTIALS") {
            setPassword("");
          }
        },
      },
    );
  }

  const showSessionExpired = sessionExpired && mutation.isIdle;
  const errorMessage = mutation.isError
    ? mutation.error.code === "INVALID_CREDENTIALS"
      ? t("signIn.error.invalidCredentials")
      : mutation.error.code === "NETWORK"
        ? tCommon("errors.network")
        : tCommon("errors.unexpected")
    : null;

  return (
    <Stack spacing={2} component="form" onSubmit={handleSubmit} noValidate>
      {showSessionExpired && (
        <Alert severity="warning" ref={alertRef} tabIndex={-1}>
          {t("signIn.sessionExpired")}
        </Alert>
      )}
      {errorMessage && (
        <Alert severity="error" ref={alertRef} tabIndex={-1}>
          {errorMessage}
        </Alert>
      )}
      <TextField
        id="signin-username"
        name="username"
        label={t("fields.username.label")}
        fullWidth
        required
        autoComplete="username"
        autoFocus={!sessionExpired}
        inputRef={usernameRef}
        value={username}
        onChange={handleUsernameChange}
        onBlur={handleUsernameBlur}
        error={Boolean(usernameError)}
        helperText={usernameError ? translateFieldError(t, usernameError) : undefined}
        disabled={mutation.isPending}
        slotProps={{ htmlInput: { maxLength: USERNAME_MAX } }}
      />
      <TextField
        id="signin-password"
        name="password"
        type="password"
        label={t("fields.password.label")}
        fullWidth
        required
        autoComplete="current-password"
        inputRef={passwordRef}
        value={password}
        onChange={handlePasswordChange}
        onBlur={handlePasswordBlur}
        error={Boolean(passwordError)}
        helperText={passwordError ? translateFieldError(t, passwordError) : undefined}
        disabled={mutation.isPending}
      />
      <Button type="submit" variant="contained" fullWidth size="large" loading={mutation.isPending}>
        {mutation.isPending ? t("signIn.submitting") : t("signIn.submit")}
      </Button>
    </Stack>
  );
}
