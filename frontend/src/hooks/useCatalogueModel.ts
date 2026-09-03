import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import type { components } from "../api/schema";
import type { UsedPrice } from "../components/usedPrice";
import { queryKeys } from "../queryKeys";

/**
 * One approved model, everything the detail page renders: the verified
 * specification, the retrieved prose, the documents behind it and its
 * photographs — one request, one payload.
 *
 * The request goes through the generated `openapi-fetch` client, so every field
 * is typed from the backend's own schema; the JSON:API envelope is unwrapped
 * here and nowhere else. The only thing this hook adds to the payload is the
 * development media prefix on the image URLs.
 *
 * An unknown **and** an unpublished id both answer 404 `not-found` — the
 * backend deliberately cannot tell them apart (no existence leak), so neither
 * does this hook: the screen gets one not-found state for both.
 */

// --- Types ------------------------------------------------------------------

/**
 * One approved image: the three variant URLs plus its attribution, in the wire's
 * own variant keys, so `ModelImageGallery` reads exactly what the API produced.
 */
export type CatalogueImage = components["schemas"]["CatalogueImage"];

/** One retrieved document behind the page — the out-of-chat provenance row. */
export type ModelSource = components["schemas"]["CatalogueSource"];

/**
 * One trim as the customer-facing payload carries it (data-model §2.5,
 * ui-spec §8 API-2) — the generated `ProductVariant` schema, landed by
 * backend step 6.20 on `CatalogueModelAttributes.variants`. Re-exported under
 * this name (rather than importing `components["schemas"]["ProductVariant"]`
 * at every call site) since step 6.27; deliberately the same generated type
 * as the admin-only `ProductVariant` in `useProductReview.ts` — the D6 claim
 * boundary is a property of `suggestion`, not of `variants`, so sharing this
 * one is fine.
 */
export type CatalogueVariant = components["schemas"]["ProductVariant"];

/**
 * Everything the detail page renders (ui-spec §4.6 "data needs"): the resource
 * id merged with its attributes.
 *
 * `specs` holds the **13 frozen fields**, every one of them explicitly nullable:
 * an approved model without a verified revision answers 13 nulls, and the table
 * omits what it does not know rather than guessing it.
 *
 * `variants` is real since backend step 6.20 (`CatalogueModelAttributes`
 * carries it, required, never absent — an unreviewed model simply has an
 * empty list).
 *
 * `usedPrice` is still `Partial` (step 6.26, ui-spec §8 API-3): the generated
 * `CatalogueModelAttributes` does not carry it until backend step 6.23 lands
 * `usedPrice` on the detail resource — 6.28 deletes this member and swaps to
 * the generated one. `null` is the defined "no researched price yet" state;
 * an absent member is the pre-6.23 payload shape.
 */
export type CatalogueModelDetail = {
  motorbikeId: string;
} & components["schemas"]["CatalogueModelAttributes"] &
  Partial<{ usedPrice: UsedPrice | null }>;

/**
 * A failed catalogue read.
 *
 * Same shape and rationale as `ProductError`: the backend's `detail` is English
 * prose for developers, so the screen decides its own message from the status —
 * 404 (unknown *or* unapproved) is the not-found state, everything else is the
 * retryable failure. Never branch on message text.
 */
export class CatalogueError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(status: number, code: string | null = null) {
    super(`Catalogue request failed with status ${status}`);
    this.name = "CatalogueError";
    this.status = status;
    this.code = code;
  }
}

/** The two error bodies these endpoints can answer with (see shared-knowledge). */
type ErrorBody =
  | components["schemas"]["ErrorDocument"]
  | components["schemas"]["HTTPValidationError"]
  | undefined;

/**
 * Shared by both catalogue hooks (the `chatError` precedent): the class lives
 * with the screen that branches on it, and the sibling list hook throws the same
 * type so a caller never has to know which endpoint failed.
 */
export function catalogueError(status: number, body: ErrorBody): CatalogueError {
  // Domain failures arrive as a JSON:API `errors[]` document; request-validation
  // 422s keep FastAPI's `{"detail": [...]}` shape and therefore have no code.
  const code =
    body !== undefined && "errors" in body && body.errors.length > 0
      ? body.errors[0].code
      : null;

  return new CatalogueError(status, code);
}

// --- Request ----------------------------------------------------------------

/**
 * Server-relative `/media/…` URLs resolve against Vite in development, where the
 * API lives on another origin — same prefix convention as `api/client.ts`.
 */
const mediaBase: string = import.meta.env.VITE_API_URL ?? "";

/**
 * The detail payload carries all three variants already (no suffix arithmetic
 * here, unlike the summary's card-only `imageUrl`); only the origin has to be
 * filled in for the cross-origin development setup.
 */
function prefixImage(image: CatalogueImage): CatalogueImage {
  return {
    thumb: mediaBase + image.thumb,
    card: mediaBase + image.card,
    detail: mediaBase + image.detail,
    attribution: image.attribution,
  };
}

/** `GET /api/catalogue-models/{motorbikeId}` — the whole page in one payload. */
async function getModel(motorbikeId: string): Promise<CatalogueModelDetail> {
  const { data, error, response } = await apiClient.GET(
    "/api/catalogue-models/{motorbike_id}",
    { params: { path: { motorbike_id: motorbikeId } } },
  );

  if (!response.ok || data === undefined) {
    throw catalogueError(response.status, error);
  }

  return {
    motorbikeId: data.data.id,
    ...data.data.attributes,
    images: data.data.attributes.images.map(prefixImage),
  };
}

// --- Hook -------------------------------------------------------------------

/**
 * One approved model with everything the detail page shows: specs, prose,
 * sources and images.
 *
 * The route param can be empty for a fraction of a render, and asking the API
 * for model "" would answer 404 and show the wrong state — hence the guard.
 */
export function useCatalogueModel(
  motorbikeId: string,
): UseQueryResult<CatalogueModelDetail, Error> {
  return useQuery({
    queryKey: queryKeys.catalogue.detail(motorbikeId),
    queryFn: () => getModel(motorbikeId),
    enabled: motorbikeId !== "",
  });
}
