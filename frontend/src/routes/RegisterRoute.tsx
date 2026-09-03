import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, Navigate, useLocation, useNavigate } from "react-router";

import { AuthError, useAuth, useRegister } from "../hooks/useAuth";

/** General errors this screen can show, keyed by the status code that caused them. */
type GeneralErrorKey = "auth.errors.serverError";

/** Field-level errors, whether the client or the server detected them. */
type FieldErrorKey =
  | "auth.errors.usernameInvalid"
  | "auth.errors.usernameTaken"
  | "auth.errors.passwordTooShort"
  | "auth.errors.passwordMismatch";

/** Mirrors the pinned username rule, applied to the lowercase-folded value. */
const USERNAME_PATTERN = /^[a-z0-9_.-]+$/;
const USERNAME_MIN_LENGTH = 3;
const USERNAME_MAX_LENGTH = 32;
const PASSWORD_MIN_LENGTH = 8;

function isUsernameValid(value: string): boolean {
  // The backend stores `username.strip().lower()`, so the folded form — not
  // what was typed — is what has to satisfy the rule.
  const normalized = value.trim().toLowerCase();

  return (
    normalized.length >= USERNAME_MIN_LENGTH &&
    normalized.length <= USERNAME_MAX_LENGTH &&
    USERNAME_PATTERN.test(normalized)
  );
}

/**
 * Registration screen, public route inside `AppLayout`.
 *
 * Validation runs on submit only — no blur or keystroke checks — which keeps
 * the controlled inputs trivial and avoids scolding someone mid-word. The first
 * invalid field takes focus so keyboard users land on the problem.
 */
export function RegisterRoute() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const register = useRegister();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [generalError, setGeneralError] = useState<GeneralErrorKey | null>(null);
  const [usernameError, setUsernameError] = useState<FieldErrorKey | null>(null);
  const [passwordError, setPasswordError] = useState<FieldErrorKey | null>(null);
  const [confirmPasswordError, setConfirmPasswordError] = useState<FieldErrorKey | null>(
    null,
  );

  const usernameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmPasswordRef = useRef<HTMLInputElement>(null);

  const isPending = register.isPending;

  // A registration can also be reached through the `RequireAuth` gate, so honour
  // the same remembered destination the login screen does.
  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;

  // Already signed in: creating a second account from an authenticated session
  // is not a flow this app has. The chained login of this very form is excluded,
  // or it would race the success navigation below and lose the destination.
  if (user !== null && !register.isSuccess) {
    return <Navigate to="/" replace />;
  }

  /**
   * Server-side rejections, by status code — never by the `detail` sentence,
   * which is English prose from FastAPI rather than a stable contract.
   */
  function handleServerError(error: Error) {
    if (error instanceof AuthError && error.status === 409) {
      setUsernameError("auth.errors.usernameTaken");
      usernameRef.current?.focus();
      return;
    }

    if (error instanceof AuthError && error.status === 422) {
      // The client checks already mirror the pinned rules, so a 422 means they
      // disagree with the server. Show it on the field the server named; if it
      // named nothing we can map, fall back to the general slot rather than
      // silently swallowing it.
      const showsUsername = error.validationFields.includes("username");
      const showsPassword = error.validationFields.includes("password");

      if (showsUsername) {
        setUsernameError("auth.errors.usernameInvalid");
      }
      if (showsPassword) {
        setPasswordError("auth.errors.passwordTooShort");
      }

      if (showsUsername || showsPassword) {
        (showsUsername ? usernameRef : passwordRef).current?.focus();
        return;
      }
    }

    setGeneralError("auth.errors.serverError");
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setGeneralError(null);

    const nextUsernameError: FieldErrorKey | null = isUsernameValid(username)
      ? null
      : "auth.errors.usernameInvalid";
    const nextPasswordError: FieldErrorKey | null =
      password.length >= PASSWORD_MIN_LENGTH ? null : "auth.errors.passwordTooShort";
    const nextConfirmPasswordError: FieldErrorKey | null =
      confirmPassword === password ? null : "auth.errors.passwordMismatch";

    setUsernameError(nextUsernameError);
    setPasswordError(nextPasswordError);
    setConfirmPasswordError(nextConfirmPasswordError);

    if (nextUsernameError !== null) {
      usernameRef.current?.focus();
      return;
    }
    if (nextPasswordError !== null) {
      passwordRef.current?.focus();
      return;
    }
    if (nextConfirmPasswordError !== null) {
      confirmPasswordRef.current?.focus();
      return;
    }

    register.mutate(
      { username, password },
      {
        // `useRegister` already chained the login, so success here means signed
        // in — no "now please log in" detour.
        onSuccess: () => {
          navigate(from ?? "/", { replace: true });
        },
        onError: handleServerError,
      },
    );
  }

  return (
    <Box sx={{ display: "flex", justifyContent: "center", pt: { xs: 2, sm: 8 } }}>
      <Paper
        component="form"
        onSubmit={handleSubmit}
        sx={{ p: 4, width: "100%", maxWidth: 400 }}
      >
        <Stack spacing={3}>
          <Typography variant="h5" component="h1">
            {t("auth.register.title")}
          </Typography>
          {generalError !== null && <Alert severity="error">{t(generalError)}</Alert>}
          <TextField
            label={t("auth.fields.username")}
            name="username"
            autoComplete="username"
            autoFocus
            required
            fullWidth
            disabled={isPending}
            error={usernameError !== null}
            helperText={
              usernameError !== null ? t(usernameError) : t("auth.register.usernameHint")
            }
            inputRef={usernameRef}
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
          <TextField
            label={t("auth.fields.password")}
            name="password"
            type="password"
            autoComplete="new-password"
            required
            fullWidth
            disabled={isPending}
            error={passwordError !== null}
            helperText={
              passwordError !== null ? t(passwordError) : t("auth.register.passwordHint")
            }
            inputRef={passwordRef}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <TextField
            label={t("auth.fields.confirmPassword")}
            name="confirmPassword"
            type="password"
            autoComplete="new-password"
            required
            fullWidth
            disabled={isPending}
            error={confirmPasswordError !== null}
            helperText={
              confirmPasswordError !== null ? t(confirmPasswordError) : undefined
            }
            inputRef={confirmPasswordRef}
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
          <Button
            type="submit"
            variant="contained"
            fullWidth
            disabled={isPending}
            startIcon={
              isPending ? <CircularProgress size={20} color="inherit" /> : undefined
            }
          >
            {t("auth.register.submit")}
          </Button>
          <Typography variant="body2">
            {t("auth.register.haveAccount")}{" "}
            <Link component={RouterLink} to="/login">
              {t("auth.register.loginLink")}
            </Link>
          </Typography>
        </Stack>
      </Paper>
    </Box>
  );
}
