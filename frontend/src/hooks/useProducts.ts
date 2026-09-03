import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { apiClient } from "../api/client";
import type { components } from "../api/schema";
import { queryKeys } from "../queryKeys";

/**
 * The catalogue's `products` resource: the backlog list plus the two writes the
 * admin UI performs on it.
 *
 * Every request goes through the generated `openapi-fetch` client, so the JSON:API
 * envelopes (`data`/`attributes`/`meta`) are typed from the backend's own schema.
 * The envelope is unwrapped here and nowhere else — components see flat rows.
 *
 * Nothing here updates optimistically: transitions are validated server-side, so
 * both mutations await the server and then invalidate, which means the screens
 * always render refetched server truth (ui-spec conventions).
 */

/** Motorbike lifecycle, from the generated `motorbike_status` enum. */
export type ProductStatus = components["schemas"]["MotorbikeStatus"];

/**
 * A row of the catalogue: the resource id merged with its attributes.
 *
 * Flattening is deliberate — `id` is JSON:API structure, everything a screen
 * renders is an attribute, and one shape means no component ever reaches into
 * `.attributes`.
 */
export type Product = { id: string } & components["schemas"]["ProductAttributes"];

/** Server-side filtering of the list query (`filter[status]`). */
export interface ProductFilters {
  status?: ProductStatus;
}

/**
 * A failed products call, carrying what the screens branch on.
 *
 * Same shape and rationale as Phase-1's `AuthError`: the backend's JSON:API
 * `detail` is English prose for developers, so the UI decides its own message
 * from the status code (409 duplicate, 422 validation, anything else "server
 * error"). `code` is the stable application code of a domain error
 * (`duplicate-model`, `invalid-transition`, `not-found`, `invalid-filter`) and is
 * `null` for the error shapes that carry none — FastAPI's request-validation 422
 * and auth/CSRF `{"detail": …}` bodies. Never branch on `detail` text.
 */
export class ProductError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(status: number, code: string | null = null) {
    super(`Products request failed with status ${status}`);
    this.name = "ProductError";
    this.status = status;
    this.code = code;
  }
}

/** The two error bodies these endpoints can answer with (see shared-knowledge). */
type ErrorBody =
  | components["schemas"]["ErrorDocument"]
  | components["schemas"]["HTTPValidationError"]
  | undefined;

function productError(status: number, body: ErrorBody): ProductError {
  // Domain failures arrive as a JSON:API `errors[]` document; request-validation
  // 422s keep FastAPI's `{"detail": [...]}` shape and therefore have no code.
  const code =
    body !== undefined && "errors" in body && body.errors.length > 0
      ? body.errors[0].code
      : null;

  return new ProductError(status, code);
}

/**
 * Pinned page size — also the server's maximum. The catalogue's ceiling is a few
 * hundred models, so the list hook walks the pages instead of paginating the UI;
 * without the walk row 101 would silently disappear.
 */
const PAGE_SIZE = 100;

function toProduct(resource: components["schemas"]["ProductResource"]): Product {
  return { id: resource.id, ...resource.attributes };
}

/** `GET /api/products`, following `meta.totalCount` to the last page. */
async function listProducts({ status }: ProductFilters): Promise<Product[]> {
  const products: Product[] = [];

  for (let page = 1; ; page += 1) {
    const { data, error, response } = await apiClient.GET("/api/products", {
      params: {
        query: {
          // Omitted rather than sent empty: an absent filter is "all statuses".
          ...(status === undefined ? {} : { "filter[status]": status }),
          "page[number]": page,
          "page[size]": PAGE_SIZE,
        },
      },
    });

    if (!response.ok || data === undefined) {
      throw productError(response.status, error);
    }

    products.push(...data.data.map(toProduct));

    // The empty-page guard is what keeps this loop finite if rows are deleted
    // between two page requests and `totalCount` stays ahead of what is left.
    if (products.length >= data.meta.totalCount || data.data.length === 0) {
      return products;
    }
  }
}

/** `POST /api/products` — a new `backlog` row; ingestion starts server-side. */
async function createProduct({ name }: { name: string }): Promise<Product> {
  const { data, error, response } = await apiClient.POST("/api/products", {
    body: { data: { type: "products", attributes: { name } } },
  });

  if (!response.ok || data === undefined) {
    // A duplicate slug answers 409 `duplicate-model`; the dialog maps it to a
    // field error on the name.
    throw productError(response.status, error);
  }

  return toProduct(data.data);
}

/** `PATCH /api/products/{id}` with a status, i.e. one transition of the matrix. */
async function transitionProduct({
  id,
  status,
}: {
  id: string;
  status: ProductStatus;
}): Promise<Product> {
  const { data, error, response } = await apiClient.PATCH("/api/products/{product_id}", {
    params: { path: { product_id: id } },
    body: { data: { type: "products", attributes: { status } } },
  });

  if (!response.ok || data === undefined) {
    // An illegal transition answers 422 `invalid-transition`, a vanished row 404.
    throw productError(response.status, error);
  }

  return toProduct(data.data);
}

/**
 * The backlog list, optionally narrowed to one status.
 *
 * The filter is part of the key rather than a client-side `select`, because the
 * filtering happens server-side and each filter therefore has its own cache
 * entry.
 */
export function useProducts(
  statusFilter?: ProductStatus,
): UseQueryResult<Product[], Error> {
  return useQuery({
    queryKey: queryKeys.products.list(statusFilter),
    queryFn: () => listProducts({ status: statusFilter }),
  });
}

/**
 * Adds a model to the backlog (`POST /api/products`; ingestion auto-starts
 * server-side).
 *
 * Invalidation lives here, not at the call site: both caches are affected by
 * every write regardless of which screen triggered it. Clearing the status
 * filter after a successful create belongs to the route, which owns the URL.
 */
export function useCreateProduct(): UseMutationResult<Product, Error, { name: string }> {
  const queryClient = useQueryClient();

  return useMutation<Product, Error, { name: string }>({
    mutationFn: createProduct,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.products.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.operations.all });
    },
  });
}

/**
 * Moves a model to another status (`PATCH /api/products/{id}`). The transition
 * matrix is enforced server-side; a rejected transition answers 422
 * `invalid-transition`. A transition to `ingesting` re-enqueues ingestion
 * server-side, which is why "start" and "retry" are the same call.
 */
export function useTransitionProduct(): UseMutationResult<
  Product,
  Error,
  { id: string; status: ProductStatus }
> {
  const queryClient = useQueryClient();

  return useMutation<Product, Error, { id: string; status: ProductStatus }>({
    mutationFn: transitionProduct,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.products.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.operations.all });
    },
  });
}
