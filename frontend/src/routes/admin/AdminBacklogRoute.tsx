import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Icon from "@mui/material/Icon";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, useSearchParams } from "react-router";

import { AddModelDialog } from "../../components/AddModelDialog";
import { EmptyState } from "../../components/EmptyState";
import { MotorbikeStatusChip } from "../../components/MotorbikeStatusChip";
import { OperationProgress } from "../../components/OperationProgress";
import { useLatestOperationsByEntity, type Operation } from "../../hooks/useOperations";
import {
  useProducts,
  useTransitionProduct,
  type Product,
  type ProductStatus,
} from "../../hooks/useProducts";

/**
 * The admin backlog: every model in the catalogue with its status, its live
 * ingestion progress and the one action its status allows.
 *
 * Two queries feed it — the filtered product list and a single operations query
 * reduced to "newest operation per model". Both are refetched by the SSE
 * listener in the app shell, which is what makes a model flip from `ingesting`
 * to `in_review` under the cursor with no reload and no polling.
 */

/** Filter options, in lifecycle order; also the whitelist for the URL param. */
const STATUS_OPTIONS: readonly ProductStatus[] = [
  "backlog",
  "ingesting",
  "in_review",
  "approved",
  "rejected",
];

/** Operation states that block a new ingestion run for the same model. */
const BUSY_OPERATION_STATUSES: readonly Operation["status"][] = ["queued", "running"];

const SKELETON_ROW_COUNT = 5;

/**
 * What to call a model: the extracted manufacturer and model name once
 * extraction has filled them in, otherwise the name the admin typed — a
 * just-added row has nothing else, and an empty first column would read as a
 * broken table.
 */
function displayName(product: Product): string {
  const extracted = [product.manufacturer, product.modelName]
    .filter((part): part is string => part !== null && part !== "")
    .join(" ");

  return extracted === "" ? product.name : extracted;
}

/** `2006–2011`, or `2014–` while a model is still in production. */
function yearRange(product: Product): string | null {
  if (product.yearFrom === null) {
    return null;
  }

  return `${product.yearFrom}–${product.yearTo ?? ""}`;
}

export function AdminBacklogRoute() {
  const { t, i18n } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);

  // The filter lives in the URL so it survives a reload and can be shared;
  // anything unrecognised counts as "no filter" rather than as an empty list.
  const statusParam = searchParams.get("status");
  const statusFilter = STATUS_OPTIONS.find((status) => status === statusParam);

  const products = useProducts(statusFilter);
  const operations = useLatestOperationsByEntity();
  const transition = useTransitionProduct();

  function setStatusFilter(status: string) {
    const params = new URLSearchParams(searchParams);

    if (status === "") {
      params.delete("status");
    } else {
      params.set("status", status);
    }

    // `replace`: a filter change is view state, so the back button must leave
    // the page instead of unwinding a series of filter clicks.
    setSearchParams(params, { replace: true });
  }

  function handleCreated() {
    setIsAddDialogOpen(false);
    // The new row is always `backlog`; keeping an unrelated filter on would
    // hide the model that was just added.
    setStatusFilter("");
  }

  function startIngestion(product: Product) {
    transition.mutate({ id: product.id, status: "ingesting" });
  }

  const addModelButton = (
    <Button
      variant="contained"
      startIcon={<Icon>add</Icon>}
      disabled={products.isLoading}
      onClick={() => setIsAddDialogOpen(true)}
    >
      {t("admin.backlog.addModel")}
    </Button>
  );

  const tableHead = (
    <TableHead>
      <TableRow>
        <TableCell>{t("admin.backlog.table.model")}</TableCell>
        <TableCell>{t("admin.backlog.table.status")}</TableCell>
        <TableCell sx={{ width: "35%" }}>{t("admin.backlog.table.progress")}</TableCell>
        <TableCell>{t("admin.backlog.table.updated")}</TableCell>
        <TableCell align="right">{t("admin.backlog.table.actions")}</TableCell>
      </TableRow>
    </TableHead>
  );

  function renderRow(product: Product) {
    const operation = operations.data?.get(product.id);
    const isBusy =
      operation !== undefined && BUSY_OPERATION_STATUSES.includes(operation.status);
    const canStartIngestion =
      (product.status === "backlog" || product.status === "rejected") && !isBusy;
    const isTransitionPending =
      transition.isPending && transition.variables?.id === product.id;
    const range = yearRange(product);

    return (
      <TableRow key={product.id}>
        <TableCell>
          <Typography variant="body2">{displayName(product)}</Typography>
          {range !== null && (
            <Typography variant="caption" color="text.secondary">
              {range}
            </Typography>
          )}
        </TableCell>
        <TableCell>
          <MotorbikeStatusChip status={product.status} />
        </TableCell>
        <TableCell>
          {operation !== undefined && operation.status !== "succeeded" && (
            <OperationProgress operation={operation} name={displayName(product)} />
          )}
        </TableCell>
        <TableCell>
          {new Date(product.updatedAt).toLocaleString(i18n.language, {
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </TableCell>
        <TableCell align="right">
          {(product.status === "in_review" || product.status === "approved") && (
            <Button size="small" component={RouterLink} to={`/admin/models/${product.id}`}>
              {t("admin.backlog.review")}
            </Button>
          )}
          {canStartIngestion && (
            <Button
              size="small"
              startIcon={
                isTransitionPending ? (
                  <CircularProgress size={20} color="inherit" />
                ) : (
                  <Icon>refresh</Icon>
                )
              }
              disabled={isTransitionPending}
              onClick={() => startIngestion(product)}
            >
              {t(
                operation?.status === "failed"
                  ? "admin.backlog.retryIngestion"
                  : "admin.backlog.startIngestion",
              )}
            </Button>
          )}
        </TableCell>
      </TableRow>
    );
  }

  function renderContent() {
    if (products.isError) {
      return (
        <EmptyState
          icon="error"
          title={t("admin.backlog.loadError")}
          body={t("common.errors.serverError")}
          action={
            <Button
              onClick={() => {
                void products.refetch();
              }}
            >
              {t("common.retry")}
            </Button>
          }
        />
      );
    }

    // First load only: a background refetch (an SSE invalidation, above all)
    // keeps the current rows on screen, because swapping live rows for
    // skeletons several times per ingestion would be unreadable.
    if (products.isLoading) {
      return (
        <TableContainer component={Paper} variant="outlined">
          <Table sx={{ minWidth: 720 }} aria-label={t("admin.backlog.table.ariaLabel")}>
            {tableHead}
            <TableBody>
              {Array.from({ length: SKELETON_ROW_COUNT }, (_, index) => (
                <TableRow key={index}>
                  {Array.from({ length: 5 }, (_unused, cellIndex) => (
                    <TableCell key={cellIndex}>
                      <Skeleton variant="text" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      );
    }

    const rows = products.data ?? [];

    if (rows.length === 0) {
      return statusFilter === undefined ? (
        <EmptyState
          icon="two_wheeler"
          title={t("admin.backlog.emptyTitle")}
          body={t("admin.backlog.emptyBody")}
          action={addModelButton}
        />
      ) : (
        <EmptyState
          icon="filter_alt_off"
          title={t("admin.backlog.emptyFilteredTitle")}
          body={t("admin.backlog.emptyFilteredBody")}
          action={
            <Button onClick={() => setStatusFilter("")}>
              {t("admin.backlog.clearFilter")}
            </Button>
          }
        />
      );
    }

    return (
      <TableContainer component={Paper} variant="outlined">
        <Table sx={{ minWidth: 720 }} aria-label={t("admin.backlog.table.ariaLabel")}>
          {tableHead}
          <TableBody>{rows.map(renderRow)}</TableBody>
        </Table>
      </TableContainer>
    );
  }

  return (
    <>
      <Stack
        direction="row"
        spacing={2}
        sx={{
          mb: 2,
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
        }}
      >
        <TextField
          select
          size="small"
          sx={{ minWidth: 200 }}
          label={t("admin.backlog.filterLabel")}
          value={statusFilter ?? ""}
          onChange={(event) => setStatusFilter(event.target.value)}
        >
          <MenuItem value="">{t("admin.backlog.filterAll")}</MenuItem>
          {STATUS_OPTIONS.map((status) => (
            <MenuItem key={status} value={status}>
              {t(`admin.status.${status}`)}
            </MenuItem>
          ))}
        </TextField>
        {addModelButton}
      </Stack>
      {/* No reserved slot: the healthy page stays unchanged, matching the
          `LiveConnectionAlert` precedent — statuses are still current, only
          their liveness is in question. */}
      {operations.isError && (
        <Alert
          severity="warning"
          icon={<Icon>sync_problem</Icon>}
          sx={{ mb: 2 }}
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => {
                void operations.refetch();
              }}
            >
              {t("common.retry")}
            </Button>
          }
        >
          {t("admin.backlog.operationsLoadError")}
        </Alert>
      )}
      {renderContent()}
      {isAddDialogOpen && (
        <AddModelDialog
          onClose={() => setIsAddDialogOpen(false)}
          onCreated={handleCreated}
        />
      )}
      {/* A rejected transition emits no SSE event, so nothing else on the page
          would otherwise show that the click failed. Success stays
          surface-free — SSE genuinely reports that outcome. */}
      <Snackbar
        open={transition.isError}
        autoHideDuration={6000}
        onClose={() => transition.reset()}
      >
        <Alert severity="error" onClose={() => transition.reset()}>
          {t("admin.backlog.transitionError")}
        </Alert>
      </Snackbar>
    </>
  );
}
