import Badge from "@mui/material/Badge";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Drawer from "@mui/material/Drawer";
import Grid from "@mui/material/Grid";
import Icon from "@mui/material/Icon";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import MenuItem from "@mui/material/MenuItem";
import Pagination from "@mui/material/Pagination";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router";

import { CatalogueFilters } from "../components/CatalogueFilters";
import { CatalogueModelCard } from "../components/CatalogueModelCard";
import { EmptyState } from "../components/EmptyState";
import {
  CATALOGUE_SORT_VALUES,
  useCatalogueFilters,
  type CatalogueSort,
} from "../hooks/useCatalogueFilters";
import { PAGE_SIZE, useCatalogueModels } from "../hooks/useCatalogueModels";

/**
 * The customer catalogue (ui-spec §3): a filtered, sorted, paginated grid of
 * approved models.
 *
 * The whole view state lives in the URL — filters, sort and page — so a reload
 * or a shared link reproduces exactly what was on screen, and the query key
 * follows from that same parsed object. Pagination is server-driven (one page
 * per request), deliberately unlike the admin screens' walk-all-pages hooks.
 */

/** Grid sizing, shared by the cards and their skeletons so nothing jumps. */
const GRID_ITEM_SIZE = { xs: 12, sm: 6, md: 4, lg: 3 } as const;

const SKELETON_CARD_COUNT = 8;

/** Sort option → its i18n key, in the order the select offers them. */
const SORT_LABELS = {
  name: "catalogue.sort.nameAsc",
  "-name": "catalogue.sort.nameDesc",
  price: "catalogue.sort.priceAsc",
  "-price": "catalogue.sort.priceDesc",
} as const satisfies Record<CatalogueSort, string>;

function isSortValue(value: string): value is CatalogueSort {
  return (CATALOGUE_SORT_VALUES as readonly string[]).includes(value);
}

/** A card-shaped placeholder: same image height and text lines as the real one. */
function SkeletonCard() {
  return (
    <Card variant="outlined">
      <Skeleton variant="rectangular" height={160} />
      <CardContent>
        <Skeleton variant="text" width="70%" />
        <Skeleton variant="text" width="45%" />
      </CardContent>
    </Card>
  );
}

export function CatalogueRoute() {
  const { t } = useTranslation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const { filters, setFilter, setPage, clearFilters, activeFilterCount } =
    useCatalogueFilters();
  const models = useCatalogueModels(filters);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const page = models.data;
  const totalCount = page?.totalCount ?? 0;
  const pageCount = Math.ceil(totalCount / PAGE_SIZE);

  function handlePageChange(nextPage: number) {
    setPage(nextPage);
    // A new page that starts mid-scroll is disorienting; filter changes, which
    // keep the reader in place, deliberately do not scroll.
    window.scrollTo({ top: 0 });
  }

  const sortSelect = (
    <TextField
      select
      size="small"
      sx={{ minWidth: 190 }}
      label={t("catalogue.sort.label")}
      value={filters.sort}
      onChange={(event) => {
        if (isSortValue(event.target.value)) {
          setFilter({ sort: event.target.value });
        }
      }}
    >
      {CATALOGUE_SORT_VALUES.map((value) => (
        <MenuItem key={value} value={value}>
          {t(SORT_LABELS[value])}
        </MenuItem>
      ))}
    </TextField>
  );

  function renderResults() {
    // An error only takes the screen when there is nothing to show: a failed
    // refetch keeps the previous grid (`keepPreviousData`) and reports itself
    // through the progress slot instead.
    if (models.isError && page === undefined) {
      return (
        <EmptyState
          icon="error"
          title={t("catalogue.list.loadError")}
          body={t("common.errors.serverError")}
          action={
            <Button
              onClick={() => {
                void models.refetch();
              }}
            >
              {t("common.retry")}
            </Button>
          }
        />
      );
    }

    if (page === undefined) {
      return (
        <Grid container spacing={2} aria-busy aria-label={t("catalogue.list.gridLabel")}>
          {Array.from({ length: SKELETON_CARD_COUNT }, (_unused, index) => (
            <Grid key={index} size={GRID_ITEM_SIZE}>
              <SkeletonCard />
            </Grid>
          ))}
        </Grid>
      );
    }

    if (page.items.length === 0) {
      // With no filter active an empty result means an empty catalogue; the way
      // models get added is the advisor, so that is the only offer here.
      return activeFilterCount === 0 ? (
        <EmptyState
          icon="two_wheeler"
          title={t("catalogue.list.emptyTitle")}
          body={t("catalogue.list.emptyBody")}
          action={
            <Button variant="contained" component={RouterLink} to="/consultations">
              {t("catalogue.list.emptyAction")}
            </Button>
          }
        />
      ) : (
        <EmptyState
          icon="filter_alt_off"
          title={t("catalogue.list.noMatchTitle")}
          body={t("catalogue.list.noMatchBody")}
          action={
            <Button onClick={clearFilters}>{t("catalogue.list.clearFilters")}</Button>
          }
        />
      );
    }

    return (
      <>
        <Grid
          container
          spacing={2}
          aria-busy={models.isFetching}
          aria-label={t("catalogue.list.gridLabel")}
        >
          {page.items.map((model) => (
            <Grid key={model.motorbikeId} size={GRID_ITEM_SIZE}>
              <CatalogueModelCard model={model} />
            </Grid>
          ))}
        </Grid>
        {pageCount > 1 && (
          <Stack alignItems="center" sx={{ mt: 3 }}>
            <Pagination
              count={pageCount}
              page={filters.page}
              shape="rounded"
              onChange={(_event, value) => handlePageChange(value)}
            />
          </Stack>
        )}
      </>
    );
  }

  return (
    <>
      <Typography variant="h4" component="h1" sx={{ mb: 2 }}>
        {t("catalogue.list.title")}
      </Typography>
      <Grid container spacing={3}>
        <Grid size={{ md: 3 }} sx={{ display: { xs: "none", md: "block" } }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <CatalogueFilters />
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, md: 9 }}>
          <Stack
            direction="row"
            spacing={2}
            sx={{
              mb: 1,
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
            }}
          >
            <Typography variant="body2" color="text.secondary">
              {page === undefined ? (
                <Skeleton width={80} />
              ) : (
                t("catalogue.list.resultCount", { count: totalCount })
              )}
            </Typography>
            <Stack direction="row" spacing={1}>
              {sortSelect}
              {isMobile && (
                <Badge badgeContent={activeFilterCount} color="primary">
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={<Icon>filter_list</Icon>}
                    onClick={() => setIsDrawerOpen(true)}
                  >
                    {t("catalogue.filters.open")}
                  </Button>
                </Badge>
              )}
            </Stack>
          </Stack>
          {/* Always reserved, so a refetch never moves the grid down 4px. */}
          <Box sx={{ height: 4, mb: 2 }}>
            {models.isFetching && (
              <LinearProgress aria-label={t("catalogue.list.loadingLabel")} />
            )}
          </Box>
          {renderResults()}
        </Grid>
      </Grid>
      {isMobile && (
        <Drawer
          anchor="right"
          open={isDrawerOpen}
          onClose={() => setIsDrawerOpen(false)}
        >
          <Box sx={{ width: 300, p: 2 }} role="dialog" aria-label={t("catalogue.filters.title")}>
            <Stack
              direction="row"
              sx={{ mb: 2, alignItems: "center", justifyContent: "space-between" }}
            >
              <Typography variant="h6" component="h2">
                {t("catalogue.filters.title")}
              </Typography>
              <IconButton
                edge="end"
                aria-label={t("catalogue.filters.close")}
                onClick={() => setIsDrawerOpen(false)}
              >
                <Icon>close</Icon>
              </IconButton>
            </Stack>
            {/* The same stack as the sidebar: filters apply immediately to the
                URL behind the drawer, so the count below stays live. */}
            <CatalogueFilters />
            <Button
              fullWidth
              variant="contained"
              sx={{ mt: 2 }}
              onClick={() => setIsDrawerOpen(false)}
            >
              {models.isFetching
                ? t("common.loading")
                : t("catalogue.filters.showResults", { count: totalCount })}
            </Button>
          </Box>
        </Drawer>
      )}
    </>
  );
}
