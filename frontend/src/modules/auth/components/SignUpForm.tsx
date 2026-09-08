// ui-spec.md §3.2, §4, §5, §6.2. A 409 is a field error on Username, not a
// form-level Alert (§5.2): it is actionable, so it reads as helperText and
// both values are kept for the user to edit.
import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { useTranslation } from "react-i18next";

import type { ApiFailure } from "../../../core/api/errors";
import { useSignUp } from "../hooks/useSignUp";
import {
  PASSWORD_MIN,
  USERNAME_MAX,
  USERNAME_MIN,
  translateFieldError,
  validatePasswordFull,
  validateUsernameFull,
  type FieldValidationError,
} from "../validation";

export function SignUpForm() {
  const { t } = useTranslation("auth");
  const { t: tCommon } = useTranslation("common");
  const mutation = useSignUp();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [usernameEdited, setUsernameEdited] = useState(false);
  const [passwordEdited, setPasswordEdited] = useState(false);
  const [usernameError, setUsernameError] = useState<FieldValidationError | null>(null);
  const [passwordError, setPasswordError] = useState<FieldValidationError | null>(null);

  const usernameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);

  // Focus a fresh submit failure that produced a form-level alert (network / 422 / 500).
  useEffect(() => {
    if (mutation.isError && mutation.error.code !== "USERNAME_TAKEN") {
      alertRef.current?.focus();
    }
  }, [mutation.error, mutation.isError]);

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
      setUsernameError(validateUsernameFull(username));
    }
  }

  function handlePasswordBlur() {
    if (passwordEdited) {
      setPasswordError(validatePasswordFull(password));
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();

    const nextUsernameError = validateUsernameFull(username);
    const nextPasswordError = validatePasswordFull(password);
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
          if (error.code === "USERNAME_TAKEN") {
            setUsernameError({ key: "signUp.error.usernameTaken" });
            usernameRef.current?.focus();
          }
        },
      },
    );
  }

  const formAlertMessage =
    mutation.isError && mutation.error.code !== "USERNAME_TAKEN"
      ? mutation.error.code === "NETWORK"
        ? tCommon("errors.network")
        : tCommon("errors.unexpected")
      : null;

  return (
    <Stack spacing={2} component="form" onSubmit={handleSubmit} noValidate>
      {formAlertMessage && (
        <Alert severity="error" ref={alertRef} tabIndex={-1}>
          {formAlertMessage}
        </Alert>
      )}
      <TextField
        id="signup-username"
        name="username"
        label={t("fields.username.label")}
        fullWidth
        required
        autoComplete="username"
        autoFocus
        inputRef={usernameRef}
        value={username}
        onChange={handleUsernameChange}
        onBlur={handleUsernameBlur}
        error={Boolean(usernameError)}
        helperText={
          usernameError
            ? translateFieldError(t, usernameError)
            : t("fields.username.hint", { min: USERNAME_MIN, max: USERNAME_MAX })
        }
        disabled={mutation.isPending}
        slotProps={{ htmlInput: { maxLength: USERNAME_MAX } }}
      />
      <TextField
        id="signup-password"
        name="password"
        type="password"
        label={t("fields.password.label")}
        fullWidth
        required
        autoComplete="new-password"
        inputRef={passwordRef}
        value={password}
        onChange={handlePasswordChange}
        onBlur={handlePasswordBlur}
        error={Boolean(passwordError)}
        helperText={
          passwordError ? translateFieldError(t, passwordError) : t("fields.password.hint", { min: PASSWORD_MIN })
        }
        disabled={mutation.isPending}
      />
      <Button type="submit" variant="contained" fullWidth size="large" loading={mutation.isPending}>
        {mutation.isPending ? t("signUp.submitting") : t("signUp.submit")}
      </Button>
    </Stack>
  );
}
