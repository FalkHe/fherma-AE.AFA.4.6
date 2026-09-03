import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, Navigate, useLocation, useNavigate } from "react-router";

import { AuthError, useAuth, useLogin } from "../hooks/useAuth";

/** General errors this screen can show, keyed by the status code that caused them. */
type GeneralErrorKey = "auth.errors.invalidCredentials" | "auth.errors.serverError";

/**
 * Sign-in screen, public route inside `AppLayout`.
 *
 * Client-side validation is deliberately limited to the browser-level
 * `required` prop: length and charset rules are the server's call on login, so
 * a stricter client check could only ever reject a credential the backend would
 * have accepted. Registration is where the pinned rules are mirrored.
 */
export function LoginRoute() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const login = useLogin();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [generalError, setGeneralError] = useState<GeneralErrorKey | null>(null);

  const usernameRef = useRef<HTMLInputElement>(null);

  const isPending = login.isPending;

  // Focus has to go back to the username field after a rejected sign-in, and it
  // has to happen *here* rather than in the mutation's `onError`: while the
  // request is in flight every input carries `disabled` (the pending state), the
  // mutation callbacks run before React commits the error render, and a browser
  // silently ignores `focus()` on a disabled element. Waiting for the commit
  // that re-enables the field is what makes the call stick.
  useEffect(() => {
    if (generalError === "auth.errors.invalidCredentials" && !isPending) {
      usernameRef.current?.focus();
    }
  }, [generalError, isPending]);

  // Where `RequireAuth` sent us from, carried in router state rather than the
  // URL — no open-redirect surface to police, and it survives the SPA redirect.
  const sentFrom = (location.state as { from?: { pathname?: string; search?: string } } | null)
    ?.from;
  const from = sentFrom?.pathname ? `${sentFrom.pathname}${sentFrom.search ?? ""}` : undefined;

  // Already signed in: the sign-in form has nothing left to offer. Rendered as
  // a redirect rather than an effect so it happens before any paint.
  //
  // Excluding the sign-in this screen just performed is not cosmetic: writing
  // the user into the cache re-renders this component, and a blanket redirect
  // here would race the success navigation below and drop the remembered
  // destination on the floor.
  if (user !== null && !login.isSuccess) {
    return <Navigate to="/" replace />;
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setGeneralError(null);

    login.mutate(
      { username, password, rememberMe },
      {
        onSuccess: () => {
          navigate(from ?? "/", { replace: true });
        },
        onError: (error) => {
          // One message for every rejected credential: telling the visitor
          // *which* half was wrong would confirm that an account exists.
          if (error instanceof AuthError && error.status === 401) {
            // The effect above returns focus to the username field once this
            // state has been committed and the field is interactive again.
            setGeneralError("auth.errors.invalidCredentials");
            setPassword("");
            return;
          }

          setGeneralError("auth.errors.serverError");
        },
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
            {t("auth.login.title")}
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
            inputRef={usernameRef}
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
          <TextField
            label={t("auth.fields.password")}
            name="password"
            type="password"
            autoComplete="current-password"
            required
            fullWidth
            disabled={isPending}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <FormControlLabel
            control={
              <Checkbox
                name="rememberMe"
                checked={rememberMe}
                disabled={isPending}
                onChange={(event) => setRememberMe(event.target.checked)}
              />
            }
            label={t("auth.login.rememberMe")}
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
            {t("auth.login.submit")}
          </Button>
          <Typography variant="body2">
            {t("auth.login.noAccount")}{" "}
            <Link component={RouterLink} to="/register">
              {t("auth.login.registerLink")}
            </Link>
          </Typography>
        </Stack>
      </Paper>
    </Box>
  );
}
