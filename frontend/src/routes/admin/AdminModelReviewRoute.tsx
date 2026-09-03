import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Icon from "@mui/material/Icon";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { useCallback, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  Link as RouterLink,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { EmptyState } from "../../components/EmptyState";
import { ModelDocumentsPanel } from "../../components/ModelDocumentsPanel";
import { ModelIdentityPanel } from "../../components/ModelIdentityPanel";
import { ModelImagePanel } from "../../components/ModelImagePanel";
import { ModelSpecsPanel } from "../../components/ModelSpecsPanel";
import { MotorbikeStatusChip } from "../../components/MotorbikeStatusChip";
import { OperationProgress } from "../../components/OperationProgress";
import { useLatestOperationsByEntity } from "../../hooks/useOperations";
import { useProduct } from "../../hooks/useProductReview";
import { ProductError, useTransitionProduct } from "../../hooks/useProducts";

/**
 * The review screen: one model, everything the ingestion produced for it, and
 * the two decisions an admin can make about it.
 *
 * It is a drill-down of the backlog rather than a section of its own, so it
 * renders inside `AdminLayout` with the Backlog tab still lit. Which of the
 * three panels is open lives in the URL (`?tab=`), as does the selected
 * document (`?doc=`) — reloading or sharing a link lands on the same view.
 *
 * Approve promotes the draft specification to verified and approves a pending
 * image, in one server-side transaction; the screen stays put afterwards
 * because seeing the published state *is* the feedback. Reject keeps documents
 * and draft (a rejected model is re-queueable) and returns to the backlog,
 * where the row now offers a retry.
 */

/**
 * Tab identifiers; also the whitelist for the `tab` search param. `identity`
 * is first in order (display-spec §6.2) but the default stays `documents` —
 * `?tab=identity` addresses it, no existing link changes behaviour.
 */
const TABS = ["identity", "documents", "specs", "image"] as const;

type ReviewTab = (typeof TABS)[number];

export function AdminModelReviewRoute() {
  const { t } = useTranslation();
  const { motorbikeId = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const product = useProduct(motorbikeId);
  const operations = useLatestOperationsByEntity();
  const transition = useTransitionProduct();

  const [dialog, setDialog] = useState<"approve" | "reject" | null>(null);
  // Owned here, reported by the specs and identity panels: the approve dialog
  // has to warn that approval publishes the last *saved* draft/identity, not
  // either form's buffer. `hasUnsavedChanges` is the OR of both (§6.2 pin).
  const [hasUnsavedSpecs, setHasUnsavedSpecs] = useState(false);
  const [hasUnsavedIdentity, setHasUnsavedIdentity] = useState(false);
  const hasUnsavedChanges = hasUnsavedSpecs || hasUnsavedIdentity;

  // Stable identity: each panel reports through its own callback from an effect.
  const handleSpecsDirtyChange = useCallback((isDirty: boolean) => {
    setHasUnsavedSpecs(isDirty);
  }, []);
  const handleIdentityDirtyChange = useCallback((isDirty: boolean) => {
    setHasUnsavedIdentity(isDirty);
  }, []);

  const tabParam = searchParams.get("tab");
  const tab: ReviewTab = TABS.find((value) => value === tabParam) ?? "documents";

  function setTab(value: ReviewTab) {
    const params = new URLSearchParams(searchParams);

    params.set("tab", value);
    // View state, like the backlog filter: the back button leaves the page
    // instead of unwinding a series of tab clicks.
    setSearchParams(params, { replace: true });
  }

  function openDialog(which: "approve" | "reject") {
    // A failure from an earlier action must not greet the next dialog.
    transition.reset();
    setDialog(which);
  }

  if (product.isLoading) {
    return (
      <Box
        role="status"
        aria-label={t("common.loading")}
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "60vh",
        }}
      >
        <CircularProgress size={48} />
      </Box>
    );
  }

  const backToBacklog = (
    <Button component={RouterLink} to="/admin">
      {t("admin.review.back")}
    </Button>
  );

  if (product.isError || product.data === undefined) {
    const status = product.error instanceof ProductError ? product.error.status : 0;

    if (status === 404) {
      return (
        <EmptyState
          icon="search_off"
          title={t("admin.review.notFoundTitle")}
          body={t("admin.review.notFoundBody")}
          action={backToBacklog}
        />
      );
    }

    return (
      <EmptyState
        icon="error"
        title={t("admin.review.loadError")}
        body={t("common.errors.serverError")}
        action={
          <Button
            onClick={() => {
              void product.refetch();
            }}
          >
            {t("common.retry")}
          </Button>
        }
      />
    );
  }

  const row = product.data;
  const operation = operations.data?.get(row.id);
  const isTransitionPending = transition.isPending;

  function transitionTo(status: "approved" | "rejected" | "ingesting") {
    transition.mutate(
      { id: row.id, status },
      {
        onSuccess: () => {
          setDialog(null);

          // A rejected model belongs to the backlog list, where its retry
          // action lives; an approved one stays here, now read-only.
          if (status === "rejected") {
            void navigate("/admin");
          }
        },
      },
    );
  }

  const tabPanels: Record<ReviewTab, ReactNode> = {
    identity: (
      <ModelIdentityPanel
        product={row}
        operation={operation}
        onDirtyChange={handleIdentityDirtyChange}
      />
    ),
    documents: <ModelDocumentsPanel product={row} />,
    specs: <ModelSpecsPanel product={row} onDirtyChange={handleSpecsDirtyChange} />,
    image: <ModelImagePanel product={row} />,
  };

  const tabsBlock = (
    <>
      <Tabs
        value={tab}
        onChange={(_event, value: ReviewTab) => setTab(value)}
        variant="scrollable"
        allowScrollButtonsMobile
        sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}
      >
        {TABS.map((value) => (
          <Tab key={value} value={value} label={t(`admin.review.tabs.${value}`)} />
        ))}
      </Tabs>
      {tabPanels[tab]}
    </>
  );

  /**
   * The page gates: an `ingesting` model has nothing to review yet, and a
   * `backlog`/`rejected` one may have leftovers from an earlier run — so those
   * two explain themselves first. Everything else reviews normally.
   */
  function renderBody() {
    if (row.status === "ingesting") {
      return (
        <Paper variant="outlined" sx={{ p: 4 }}>
          <Stack spacing={2}>
            <Typography variant="h6">{t("admin.review.ingestingTitle")}</Typography>
            {operation !== undefined && (
              <OperationProgress operation={operation} name={row.name} />
            )}
            <Typography variant="body2" color="text.secondary">
              {t("admin.review.ingestingBody")}
            </Typography>
          </Stack>
        </Paper>
      );
    }

    if (row.status === "backlog" || row.status === "rejected") {
      return (
        <>
          <Alert
            severity="info"
            sx={{ mb: 2 }}
            action={
              <Button
                size="small"
                disabled={isTransitionPending}
                startIcon={
                  isTransitionPending ? (
                    <CircularProgress size={20} color="inherit" />
                  ) : (
                    <Icon>refresh</Icon>
                  )
                }
                onClick={() => transitionTo("ingesting")}
              >
                {t(
                  operation?.status === "failed"
                    ? "admin.backlog.retryIngestion"
                    : "admin.backlog.startIngestion",
                )}
              </Button>
            }
          >
            {t("admin.review.backlogNotice")}
          </Alert>
          {operation?.status === "failed" && (
            <Box sx={{ mb: 2 }}>
              <OperationProgress operation={operation} name={row.name} />
            </Box>
          )}
          {tabsBlock}
        </>
      );
    }

    return (
      <>
        {row.status === "approved" && (
          <Alert severity="success" sx={{ mb: 2 }}>
            {t("admin.review.approvedNotice")}
          </Alert>
        )}
        {tabsBlock}
      </>
    );
  }

  return (
    <>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/admin">
          {t("admin.review.back")}
        </Link>
        <Typography color="text.primary">{row.name}</Typography>
      </Breadcrumbs>
      <Stack
        direction="row"
        spacing={2}
        sx={{ alignItems: "center", flexWrap: "wrap", mb: 2 }}
      >
        <Typography variant="h5" component="h2">
          {row.name}
        </Typography>
        <MotorbikeStatusChip status={row.status} />
        <Box sx={{ flexGrow: 1 }} />
        {row.status === "in_review" && (
          <>
            <Button
              variant="outlined"
              color="error"
              onClick={() => openDialog("reject")}
            >
              {t("admin.review.actions.reject")}
            </Button>
            <Button
              variant="contained"
              color="primary"
              startIcon={<Icon>publish</Icon>}
              onClick={() => openDialog("approve")}
            >
              {t("admin.review.actions.approve")}
            </Button>
          </>
        )}
      </Stack>
      {renderBody()}
      {dialog === "approve" && (
        <ConfirmDialog
          title={t("admin.review.actions.approveConfirmTitle")}
          body={t("admin.review.actions.approveConfirmBody")}
          warning={
            hasUnsavedChanges ? t("admin.review.actions.unsavedWarning") : undefined
          }
          confirmLabel={t("admin.review.actions.confirmApprove")}
          confirmColor="primary"
          isPending={isTransitionPending}
          hasError={transition.isError}
          errorMessage={
            transition.error instanceof ProductError && transition.error.code === "incomplete-identity"
              ? t("admin.review.approveBlockedIdentity")
              : undefined
          }
          onConfirm={() => transitionTo("approved")}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "reject" && (
        <ConfirmDialog
          title={t("admin.review.actions.rejectConfirmTitle")}
          body={t("admin.review.actions.rejectConfirmBody")}
          confirmLabel={t("admin.review.actions.confirmReject")}
          confirmColor="error"
          isPending={isTransitionPending}
          hasError={transition.isError}
          onConfirm={() => transitionTo("rejected")}
          onClose={() => setDialog(null)}
        />
      )}
    </>
  );
}
