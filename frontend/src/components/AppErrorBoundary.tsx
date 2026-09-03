import Button from "@mui/material/Button";
import Icon from "@mui/material/Icon";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "./EmptyState";

/**
 * One app-level boundary for React render crashes, mounted once around
 * `<App />` in `main.tsx`. It catches nothing else: query/mutation errors
 * keep their landed per-screen `EmptyState`/Snackbar surfaces (no
 * `throwOnError` anywhere) — a render crash is a different failure class from
 * a failed request, and this component exists only for the former.
 *
 * A class component is required here (`getDerivedStateFromError` /
 * `componentDidCatch` have no hook equivalent) — this is stock React, not a
 * new dependency. The error object itself is never rendered, matching the
 * backend's generic 500: the fallback shows a translated title/body/action
 * and nothing exception-derived.
 */

/** The fallback itself, split out so it can use `useTranslation`. */
function ErrorFallback() {
  const { t } = useTranslation();

  return (
    <EmptyState
      icon="error"
      title={t("common.errors.crashTitle")}
      body={t("common.errors.crashBody")}
      action={
        <Button
          variant="contained"
          startIcon={<Icon>refresh</Icon>}
          onClick={() => {
            window.location.reload();
          }}
        >
          {t("common.errors.crashReload")}
        </Button>
      }
    />
  );
}

export class AppErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("Unhandled render error", error, errorInfo);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return <ErrorFallback />;
    }

    return this.props.children;
  }
}
