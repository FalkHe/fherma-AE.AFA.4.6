import type { components } from "../api/schema";

import { jsonResponse } from "./network";

/**
 * A fake `catalogue-models` API for the catalogue screens.
 *
 * Step 4.9 replaced the two stub hooks with the generated client, so the
 * fixtures the list and detail tests are written against moved here — together
 * with the filtering, sorting and paging the stub used to do, now expressed in
 * the **wire** vocabulary (`filter[engineCcMin]`, `sort=msrpEur`,
 * `page[number]`). That is deliberate: the tests now exercise the real request
 * path, including the SPA-param → wire-param mapping the hook owns, and the
 * on-screen assertions in `CatalogueRoute.test.tsx` /
 * `CatalogueModelRoute.test.tsx` stayed exactly as they were written on stubs.
 *
 * Install it with `stubFetch(catalogueApi)`; anything it does not serve keeps
 * failing loudly, as the default handler does.
 */

type SummaryAttributes = components["schemas"]["CatalogueModelSummaryAttributes"];
/**
 * `variants` is real since backend step 6.20 (`CatalogueModelAttributes`
 * carries it, required — every fixture below now supplies it, `[]` where
 * there is none).
 */
type ModelAttributes = components["schemas"]["CatalogueModelAttributes"] & {
  /**
   * `usedPrice` (data-model §2.5-adjacent, ui-spec §8 API-3) is a local
   * addition — the generated `CatalogueModelAttributes` does not carry it
   * until backend step 6.23 lands, same "local member, deleted by 6.28"
   * pattern noted on `useCatalogueModel.ts`'s `CatalogueModelDetail`.
   */
  usedPrice?: {
    medianEur: number;
    minEur: number;
    maxEur: number;
    sampleCount: number | null;
    asOf: string;
    stale: boolean;
    sources: { title: string; url: string }[];
  } | null;
};
type SpecCategory = components["schemas"]["SpecCategory"];
type PriceBand = components["schemas"]["PriceBand"];

/** Fixture ids, 26 characters like the ULID primary keys they stand in for. */
function fixtureId(label: string): string {
  return `01STUB${label.toUpperCase()}`.padEnd(26, "0").slice(0, 26);
}

const MANUFACTURERS: readonly { id: string; name: string }[] = [
  { id: fixtureId("mfrbmw"), name: "BMW" },
  { id: fixtureId("mfrhonda"), name: "Honda" },
  { id: fixtureId("mfrsuzuki"), name: "Suzuki" },
  { id: fixtureId("mfryamaha"), name: "Yamaha" },
];

const MANUFACTURER_BY_NAME = new Map(
  MANUFACTURERS.map((manufacturer) => [manufacturer.name, manufacturer]),
);

/**
 * Real approved images from the development media directory — the same
 * `/media/motorbikes/{motorbikeId}/{imageId}_card.webp` shape the endpoint
 * returns, so the hook's `_card` → `_thumb` swap is exercised for real.
 */
const IMAGE_PATHS: readonly string[] = [
  "/media/motorbikes/01M10X5YWZ0T0TAKAV58MNKWFJ/01M10X642K3JCH395BA9VXET28_card.webp",
  "/media/motorbikes/01M10YCXRBW5ANBJT5MK638EK5/01M10YD8Q3CJ4BT4F00TAMNMP3_card.webp",
  "/media/motorbikes/01M10WSCDCVD8P5AG7AWVEXWJK/01M10WSKNMZ3ZP9FEX7JPMQ7AW_card.webp",
  "/media/motorbikes/01M112N358BYCK15Y6E3ZGS75V/01M112P80J0ZKG35ZDMVASJZVB_card.webp",
];

/** A fixture row: the summary payload plus the manufacturer id the filter uses. */
type FixtureModel = SummaryAttributes & { id: string; manufacturerId: string | null };

function fixture(
  key: string,
  name: string,
  manufacturerName: string | null,
  category: SpecCategory | null,
  priceBand: PriceBand | null,
  specs: {
    engineCc?: number;
    powerKw?: number;
    wetWeightKg?: number;
    seatHeightMm?: number;
    msrpEur?: number;
    a2Eligible?: boolean;
  },
  imageIndex: number | null,
): FixtureModel {
  const manufacturer =
    manufacturerName === null ? undefined : MANUFACTURER_BY_NAME.get(manufacturerName);

  return {
    id: fixtureId(key),
    name,
    manufacturer: manufacturer?.name ?? null,
    manufacturerId: manufacturer?.id ?? null,
    category,
    priceBand,
    engineCc: specs.engineCc ?? null,
    powerKw: specs.powerKw ?? null,
    wetWeightKg: specs.wetWeightKg ?? null,
    seatHeightMm: specs.seatHeightMm ?? null,
    a2Eligible: specs.a2Eligible ?? null,
    msrpEur: specs.msrpEur ?? null,
    imageUrl: imageIndex === null ? null : IMAGE_PATHS[imageIndex],
  };
}

/**
 * 29 models — more than one page, so pagination is real — spread across four
 * manufacturers, nine categories and all four price bands, so every filter
 * visibly narrows the grid. Deliberate outliers: several models without an
 * image (fallback box), one without a manufacturer (no separator line) and one
 * with no specs at all (name and manufacturer only).
 */
const MODELS: readonly FixtureModel[] = [
  fixture("bmwf850gs", "BMW F 850 GS", "BMW", "adventure", "upper", { engineCc: 853, powerKw: 70, wetWeightKg: 229, seatHeightMm: 860, msrpEur: 13200, a2Eligible: false }, 0),
  fixture("bmwf900r", "BMW F 900 R", "BMW", "naked", "upper", { engineCc: 895, powerKw: 77, wetWeightKg: 211, seatHeightMm: 815, msrpEur: 11400, a2Eligible: false }, 2),
  fixture("bmwg310r", "BMW G 310 R", "BMW", "naked", "budget", { engineCc: 313, powerKw: 25, wetWeightKg: 158, seatHeightMm: 785, msrpEur: 4990, a2Eligible: true }, 3),
  fixture("bmwr1250gs", "BMW R 1250 GS", "BMW", "adventure", "premium", { engineCc: 1254, powerKw: 100, wetWeightKg: 249, seatHeightMm: 850, msrpEur: 19900, a2Eligible: false }, 1),
  fixture("bmwninet", "BMW R nineT", "BMW", "classic", "premium", { engineCc: 1170, powerKw: 80, wetWeightKg: 221, seatHeightMm: 805, msrpEur: 16400, a2Eligible: false }, null),
  fixture("bmws1000xr", "BMW S 1000 XR", "BMW", "sport_touring", "premium", { engineCc: 999, powerKw: 121, wetWeightKg: 226, seatHeightMm: 840, msrpEur: 18500, a2Eligible: false }, 0),
  fixture("hondaafricatwin", "Honda CRF1100L Africa Twin", "Honda", "adventure", "upper", { engineCc: 1084, powerKw: 75, wetWeightKg: 226, seatHeightMm: 850, msrpEur: 14800, a2Eligible: false }, 0),
  fixture("hondacb125r", "Honda CB125R", "Honda", "naked", "budget", { engineCc: 125, powerKw: 11, wetWeightKg: 130, seatHeightMm: 816, msrpEur: 4700, a2Eligible: true }, 0),
  fixture("hondacb500f", "Honda CB500F", "Honda", "naked", "mid", { engineCc: 471, powerKw: 35, wetWeightKg: 189, seatHeightMm: 785, msrpEur: 6800, a2Eligible: true }, 1),
  fixture("hondacb650r", "Honda CB650R", "Honda", "naked", "mid", { engineCc: 649, powerKw: 70, wetWeightKg: 202, seatHeightMm: 810, msrpEur: 8900, a2Eligible: false }, 2),
  fixture("hondacbr600rr", "Honda CBR600RR", "Honda", "sport", "upper", { engineCc: 599, powerKw: 89, wetWeightKg: 194, seatHeightMm: 820, msrpEur: 13400, a2Eligible: false }, 3),
  fixture("hondarebel500", "Honda Rebel 500", "Honda", "cruiser", "mid", { engineCc: 471, powerKw: 34, wetWeightKg: 191, seatHeightMm: 690, msrpEur: 6500, a2Eligible: true }, null),
  fixture("hondatransalp", "Honda XL750 Transalp", "Honda", "adventure", "upper", { engineCc: 755, powerKw: 67, wetWeightKg: 208, seatHeightMm: 850, msrpEur: 10500, a2Eligible: false }, 1),
  fixture("sinnisterrain", "Sinnis Terrain 380", null, "scrambler", "budget", { engineCc: 378, powerKw: 29, wetWeightKg: 172, seatHeightMm: 835, msrpEur: 4400, a2Eligible: true }, null),
  fixture("suzukiburgman", "Suzuki Burgman 400", "Suzuki", "scooter", "mid", { engineCc: 400, powerKw: 22, wetWeightKg: 218, seatHeightMm: 755, msrpEur: 7900, a2Eligible: true }, 3),
  fixture("suzukidrz400", "Suzuki DR-Z400S", "Suzuki", "enduro", "mid", { engineCc: 398, powerKw: 29, wetWeightKg: 144, seatHeightMm: 935, msrpEur: 7200, a2Eligible: true }, null),
  fixture("suzukigsr600", "Suzuki GSR 600", "Suzuki", "naked", "budget", { engineCc: 599, powerKw: 72.5, wetWeightKg: 197, seatHeightMm: 785, msrpEur: 4200, a2Eligible: false }, 3),
  fixture("suzukigsx8s", "Suzuki GSX-8S", "Suzuki", null, null, {}, null),
  fixture("suzukigsxr750", "Suzuki GSX-R750", "Suzuki", "sport", "upper", { engineCc: 750, powerKw: 110, wetWeightKg: 190, seatHeightMm: 810, msrpEur: 12800, a2Eligible: false }, 1),
  fixture("suzukikatana", "Suzuki Katana", "Suzuki", "naked", "upper", { engineCc: 999, powerKw: 112, wetWeightKg: 215, seatHeightMm: 825, msrpEur: 13900, a2Eligible: false }, 2),
  fixture("suzukisv650", "Suzuki SV650", "Suzuki", "naked", "mid", { engineCc: 645, powerKw: 56, wetWeightKg: 198, seatHeightMm: 785, msrpEur: 7300, a2Eligible: true }, 0),
  fixture("suzukivstrom650", "Suzuki V-Strom 650", "Suzuki", "adventure", "mid", { engineCc: 645, powerKw: 52, wetWeightKg: 216, seatHeightMm: 835, msrpEur: 9200, a2Eligible: false }, null),
  fixture("yamahamt07", "Yamaha MT-07", "Yamaha", "naked", "mid", { engineCc: 689, powerKw: 54, wetWeightKg: 184, seatHeightMm: 805, msrpEur: 8200, a2Eligible: false }, 2),
  fixture("yamahamt09", "Yamaha MT-09", "Yamaha", "naked", "upper", { engineCc: 890, powerKw: 87, wetWeightKg: 193, seatHeightMm: 825, msrpEur: 10900, a2Eligible: false }, 3),
  fixture("yamahamt125", "Yamaha MT-125", "Yamaha", "naked", "budget", { engineCc: 124, powerKw: 11, wetWeightKg: 142, seatHeightMm: 810, msrpEur: 4900, a2Eligible: true }, null),
  fixture("yamahatenere700", "Yamaha Ténéré 700", "Yamaha", "adventure", "upper", { engineCc: 689, powerKw: 54, wetWeightKg: 204, seatHeightMm: 875, msrpEur: 11200, a2Eligible: false }, 1),
  fixture("yamahatracer9", "Yamaha Tracer 9", "Yamaha", "sport_touring", "upper", { engineCc: 890, powerKw: 87, wetWeightKg: 213, seatHeightMm: 810, msrpEur: 13500, a2Eligible: false }, 2),
  fixture("yamahaxsr700", "Yamaha XSR700", "Yamaha", "classic", "mid", { engineCc: 689, powerKw: 54, wetWeightKg: 188, seatHeightMm: 835, msrpEur: 9100, a2Eligible: false }, null),
  fixture("yamahayzfr7", "Yamaha YZF-R7", "Yamaha", "sport", "upper", { engineCc: 689, powerKw: 54, wetWeightKg: 188, seatHeightMm: 835, msrpEur: 10200, a2Eligible: false }, 0),
];

/**
 * Two `##` sections, a GFM table and an inline `<script>`: the fixture that
 * proves the pinned markdown configuration. Raw HTML is **off**, so the script
 * tag reaches the page as text and never as an element — this is retrieved web
 * content, and the article block is where that rule has to hold.
 */
const GSR600_ARTICLE = `The **Suzuki GSR 600** is a naked bike built from 2006 to 2011, using a
detuned version of the [GSX-R600](https://en.wikipedia.org/wiki/Suzuki_GSX-R600)
inline-four. <script>window.__catalogueStubPwned = true;</script>

## Design

The GSR 600 pairs a bikini fairing with an underseat exhaust; the riding
position is upright, and the frame is a twin-spar aluminium unit.

| Year | Change |
| --- | --- |
| 2006 | Launched in Europe |
| 2007 | ABS offered as an option |
| 2011 | Replaced by the GSR 750 |

## Reception

Reviewers praised the engine's mid-range and the low seat height, while
criticising the budget suspension on early bikes.`;

/** The three variant URLs of one approved image, as the API computes them. */
function imageVariants(
  cardPath: string,
  attribution: string | null,
): components["schemas"]["CatalogueImage"] {
  return {
    thumb: cardPath.replace(/_card\.webp$/, "_thumb.webp"),
    card: cardPath,
    detail: cardPath.replace(/_card\.webp$/, "_detail.webp"),
    attribution,
  };
}

/**
 * Detail fixtures: a fully-populated model and a partially-extracted one. Every
 * other id answers 404, which is also how an unpublished model behaves.
 */
const DETAILS: Record<string, ModelAttributes> = {
  [fixtureId("suzukigsr600")]: {
    name: "Suzuki GSR 600",
    manufacturer: "Suzuki",
    // 13 of 13 — every group renders, both boolean spellings appear.
    specs: {
      category: "naked",
      engineCc: 599,
      cylinders: 4,
      powerKw: 72.5,
      torqueNm: 63.5,
      wetWeightKg: 197,
      seatHeightMm: 785,
      tankCapacityL: 16.5,
      topSpeedKmh: 230,
      abs: true,
      a2Eligible: false,
      priceBand: "budget",
      msrpEur: 4200,
    },
    // Two trims — one description-only (chip row only), one carrying a
    // spec delta (chip row + one `ModelSpecTable` trims-group row).
    variants: [
      {
        slug: "comfort",
        name: "Comfort",
        description: "Adds a taller screen and heated grips.",
        specs: null,
      },
      {
        slug: "sport",
        name: "Sport",
        description: "Adjustable suspension and a sportier seat.",
        specs: { wetWeightKg: 192, seatHeightMm: 800 },
      },
    ],
    article: GSR600_ARTICLE,
    // Three rows, two of which are the interesting ones: an upload without a
    // URL, and a duplicate of the Wikipedia URL that de-duplication removes.
    sources: [
      {
        sourceTitle: "Suzuki GSR600 — Wikipedia",
        sourceUrl: "https://en.wikipedia.org/wiki/Suzuki_GSR600",
      },
      {
        sourceTitle: "Suzuki GSR600 (mirror)",
        sourceUrl: "https://en.wikipedia.org/wiki/Suzuki_GSR600",
      },
      { sourceTitle: "Owner's manual (uploaded)", sourceUrl: null },
    ],
    images: [
      imageVariants(IMAGE_PATHS[2], "Photo: Wikimedia Commons, CC BY-SA 4.0"),
      imageVariants(IMAGE_PATHS[3], null),
    ],
    // A researched used-price snapshot (ui-spec §4.2) — present and not stale.
    usedPrice: {
      medianEur: 4800,
      minEur: 3900,
      maxEur: 5600,
      sampleCount: 14,
      asOf: "2026-07-01T00:00:00Z",
      stale: false,
      sources: [
        { title: "kleinanzeigen.de", url: "https://www.kleinanzeigen.de/s-anzeige/example" },
        { title: "mobile.de", url: "https://suchen.mobile.de/example" },
      ],
    },
  },
  [fixtureId("hondarebel500")]: {
    name: "Honda Rebel 500",
    manufacturer: "Honda",
    // Partial extraction: the "Licence & safety" group is entirely unknown, so
    // it renders no header at all, and the unknown fields render no rows.
    specs: {
      category: "cruiser",
      engineCc: 471,
      cylinders: null,
      powerKw: 34,
      torqueNm: null,
      wetWeightKg: 191,
      seatHeightMm: 690,
      tankCapacityL: null,
      topSpeedKmh: null,
      abs: null,
      a2Eligible: null,
      priceBand: "mid",
      msrpEur: 6500,
    },
    article: null,
    sources: [
      {
        sourceTitle: "Honda Rebel 500 — Wikipedia",
        sourceUrl: "https://en.wikipedia.org/wiki/Honda_Rebel",
      },
    ],
    images: [],
    variants: [],
  },
};

// --- The endpoint behaviour -------------------------------------------------

function members(raw: string | null): string[] {
  return raw === null ? [] : raw.split(",").filter((member) => member !== "");
}

/**
 * The pinned NULL-spec browse rule: a NULL value never matches a stated bound,
 * so a model without that verified figure drops out of a filtered result and
 * stays in the unfiltered one.
 */
function withinBounds(
  value: number | null,
  min: string | null,
  max: string | null,
): boolean {
  if (min === null && max === null) {
    return true;
  }
  if (value === null) {
    return false;
  }

  return (
    (min === null || value >= Number(min)) && (max === null || value <= Number(max))
  );
}

function matches(model: FixtureModel, query: URLSearchParams): boolean {
  const categories = members(query.get("filter[category]"));
  const bands = members(query.get("filter[priceBand]"));
  const manufacturers = members(query.get("filter[manufacturer]"));

  if (categories.length > 0 && (model.category === null || !categories.includes(model.category))) {
    return false;
  }
  if (bands.length > 0 && (model.priceBand === null || !bands.includes(model.priceBand))) {
    return false;
  }
  if (
    manufacturers.length > 0 &&
    (model.manufacturerId === null || !manufacturers.includes(model.manufacturerId))
  ) {
    return false;
  }
  if (query.get("filter[a2Eligible]") === "true" && model.a2Eligible !== true) {
    return false;
  }

  return (
    withinBounds(
      model.engineCc,
      query.get("filter[engineCcMin]"),
      query.get("filter[engineCcMax]"),
    ) &&
    withinBounds(
      model.powerKw,
      query.get("filter[powerKwMin]"),
      query.get("filter[powerKwMax]"),
    ) &&
    withinBounds(model.seatHeightMm, null, query.get("filter[seatHeightMmMax]")) &&
    withinBounds(model.wetWeightKg, null, query.get("filter[wetWeightKgMax]"))
  );
}

/** The pinned ordering: price sorts put models without a price last. */
function compare(a: FixtureModel, b: FixtureModel, sort: string): number {
  if (sort === "name" || sort === "-name") {
    return (sort === "name" ? 1 : -1) * a.name.localeCompare(b.name);
  }

  if (a.msrpEur === null || b.msrpEur === null) {
    return a.msrpEur === b.msrpEur ? a.name.localeCompare(b.name) : a.msrpEur === null ? 1 : -1;
  }
  if (a.msrpEur === b.msrpEur) {
    return a.name.localeCompare(b.name);
  }

  return (sort === "msrpEur" ? 1 : -1) * (a.msrpEur - b.msrpEur);
}

function listResponse(query: URLSearchParams): Response {
  const matching = MODELS.filter((model) => matches(model, query));
  const sorted = [...matching].sort((a, b) =>
    compare(a, b, query.get("sort") ?? "name"),
  );
  const size = Number(query.get("page[size]") ?? "24");
  const offset = (Number(query.get("page[number]") ?? "1") - 1) * size;

  return jsonResponse({
    data: sorted.slice(offset, offset + size).map(({ id, manufacturerId, ...attributes }) => {
      void manufacturerId;

      return { id, type: "catalogue-models", attributes };
    }),
    meta: { totalCount: matching.length },
  });
}

function detailResponse(motorbikeId: string): Response {
  const attributes = DETAILS[motorbikeId];

  if (attributes === undefined) {
    // Unknown and unpublished are deliberately indistinguishable.
    return jsonResponse(
      {
        errors: [
          { status: "404", code: "not-found", detail: "Motorbike not found." },
        ],
      },
      { status: 404 },
    );
  }

  return jsonResponse({
    data: { id: motorbikeId, type: "catalogue-models", attributes },
  });
}

function manufacturersResponse(): Response {
  return jsonResponse({
    data: MANUFACTURERS.map(({ id, name }) => ({
      id,
      type: "manufacturers",
      attributes: {
        name,
        slug: name.toLowerCase(),
        description: null,
        logoPath: null,
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
      },
    })),
    meta: { totalCount: MANUFACTURERS.length },
  });
}

/** The fetch handler: `stubFetch(catalogueApi)` in a `beforeEach`. */
export function catalogueApi(request: Request): Response {
  const url = new URL(request.url);

  if (url.pathname === "/api/catalogue-models") {
    return listResponse(url.searchParams);
  }
  if (url.pathname.startsWith("/api/catalogue-models/")) {
    return detailResponse(url.pathname.slice("/api/catalogue-models/".length));
  }
  if (url.pathname === "/api/manufacturers") {
    return manufacturersResponse();
  }

  throw new Error(`The catalogue fake does not serve ${request.method} ${url.pathname}`);
}
