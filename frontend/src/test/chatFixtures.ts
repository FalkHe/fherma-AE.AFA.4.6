import type {
  ChatMessage,
  MessageSource,
  Recommendation,
  ToolCall,
} from "../hooks/useChatMessages";

/**
 * The "kitchen-sink" assistant message of ui-spec §12, and its parts.
 *
 * Every fixture here is typed against the generated client, and its **keys are
 * the pinned contract**: `tool_calls[]`, `sources[]` and `recommendations[]`
 * follow shared-knowledge §"Persisted JSONB shapes", and every tool result
 * follows §"Tool result schemas" — including the keys the renderers do not
 * read (`totalCount`, `coefficientsVersion`, `status`, …). That makes this file
 * the frontend's contract test for the agent loop's persisted output: when the
 * backend's writers change shape, these fixtures are what must be re-agreed,
 * not quietly bent.
 */

export const catalogueSearchCall: ToolCall = {
  id: "01TOOLCALL0000000000000001",
  tool: "catalogue_search",
  arguments: { categories: ["naked"], powerKwMax: 35, a2Eligible: true },
  result: {
    results: [
      {
        motorbikeId: "01BIKECB500F00000000000001",
        name: "Honda CB500F",
        category: "naked",
        powerKw: 35.0,
        wetWeightKg: 189.0,
        seatHeightMm: 785,
        priceBand: "mid",
      },
      {
        motorbikeId: "01BIKEZ650000000000000001",
        name: "Kawasaki Z650",
        category: "naked",
        powerKw: 50.2,
        wetWeightKg: 187.0,
        seatHeightMm: 790,
        priceBand: "mid",
      },
      {
        // A model whose specs were never verified: no fragments, no guesses.
        motorbikeId: "01BIKESVELTE0000000000001",
        name: "Moto Morini Seiemmezzo",
        category: null,
        powerKw: null,
        wetWeightKg: null,
        seatHeightMm: null,
        priceBand: null,
      },
    ],
    totalCount: 3,
  },
  status: "succeeded",
  error: null,
};

export const specComparisonCall: ToolCall = {
  id: "01TOOLCALL0000000000000002",
  tool: "spec_comparison",
  arguments: { names: ["Honda CB500F", "Yamaha MT-07", "Kawasaki Z650"] },
  result: {
    bikes: [
      { motorbikeId: "01BIKECB500F00000000000001", name: "Honda CB500F" },
      { motorbikeId: "01BIKEMT07000000000000001", name: "Yamaha MT-07" },
      { motorbikeId: "01BIKEZ650000000000000001", name: "Kawasaki Z650" },
    ],
    // Every frozen spec field is present; unverified values are explicit nulls.
    rows: [
      { field: "category", values: ["naked", "naked", "naked"] },
      { field: "engineCc", values: [471, 689, 649] },
      { field: "cylinders", values: [2, 2, 2] },
      { field: "powerKw", values: [35.0, 54.0, 50.2] },
      { field: "torqueNm", values: [43.0, 67.0, null] },
      { field: "wetWeightKg", values: [189.0, 184.0, 187.0] },
      { field: "seatHeightMm", values: [785, 805, null] },
      { field: "tankCapacityL", values: [17.1, 13.0, 15.0] },
      { field: "topSpeedKmh", values: [null, 200, null] },
      { field: "abs", values: [true, true, false] },
      { field: "a2Eligible", values: [true, false, false] },
      { field: "priceBand", values: ["mid", "mid", "mid"] },
      { field: "msrpEur", values: [6790, 8299, null] },
    ],
  },
  status: "succeeded",
  error: null,
};

export const licenceFitCheckCall: ToolCall = {
  id: "01TOOLCALL0000000000000003",
  tool: "licence_fit_check",
  arguments: { name: "Yamaha MT-07", licence: "A2", insideLegMm: 780 },
  result: {
    motorbikeId: "01BIKEMT07000000000000001",
    name: "Yamaha MT-07",
    rules: [
      {
        rule: "a2_power",
        label: "A2 power limit",
        verdict: "pass",
        evidence: "35.0 kW ≤ 35 kW",
      },
      {
        rule: "a2_power_to_weight",
        label: "A2 power-to-weight limit",
        verdict: "fail",
        evidence: "54.0 kW / 184 kg = 0.293 kW/kg > 0.20 kW/kg",
      },
      {
        rule: "seat_height_fit",
        label: "Seat height fit",
        verdict: "unknown",
        evidence: "Seat height not verified for this model.",
      },
    ],
  },
  status: "succeeded",
  error: null,
};

export const costEstimatorCall: ToolCall = {
  id: "01TOOLCALL0000000000000004",
  tool: "cost_estimator",
  arguments: { name: "Honda CB500F", annualKm: 8000 },
  result: {
    motorbikeId: "01BIKECB500F00000000000001",
    name: "Honda CB500F",
    currency: "EUR",
    lineItems: [
      { label: "Purchase price", amount: 6790 },
      { label: "Insurance /year", amount: 620 },
      { label: "Maintenance /year", amount: 380 },
      { label: "Riding gear (one-off)", amount: 900 },
    ],
    total: 8690,
    assumptions: [
      "8,000 km per year in Germany.",
      "Third-party insurance for a rider aged 30+ with no claims.",
      "Dealer servicing at manufacturer intervals.",
    ],
    coefficientsVersion: "2026.1",
  },
  status: "succeeded",
  error: null,
};

/**
 * The same estimate, with a researched used-price snapshot attached
 * (shared-knowledge D11, ui-spec §4.3/§8 API-4) — additive, so every field
 * `costEstimatorCall` already carries stays byte-identical.
 */
export const costEstimatorCallWithUsedPrice: ToolCall = {
  ...costEstimatorCall,
  id: "01TOOLCALL0000000000000008",
  result: {
    ...(costEstimatorCall.result as Record<string, unknown>),
    usedPrice: {
      medianEur: 4800,
      minEur: 3900,
      maxEur: 5600,
      sampleCount: 14,
      asOf: "2026-07-01T00:00:00Z",
      stale: true,
      sources: [
        { title: "kleinanzeigen.de", url: "https://www.kleinanzeigen.de/s-anzeige/example" },
        { title: "mobile.de", url: "https://suchen.mobile.de/example" },
      ],
    },
  },
  status: "succeeded",
  error: null,
};

export const recordPreferenceCall: ToolCall = {
  id: "01TOOLCALL0000000000000005",
  tool: "record_preference",
  arguments: { attribute: "budget", value: "up to €7,000", firmness: "hard" },
  result: { attribute: "budget", value: "up to €7,000", firmness: "hard" },
  status: "succeeded",
  error: null,
};

export const flagUnknownBikeCall: ToolCall = {
  id: "01TOOLCALL0000000000000006",
  tool: "flag_unknown_bike",
  arguments: { name: "Bimota Tesi H2" },
  result: { name: "Bimota Tesi H2", status: "queued" },
  status: "succeeded",
  error: null,
};

/** A tool this build predates — the §8.6 generic renderer's reason to exist. */
export const unknownToolCall: ToolCall = {
  id: "01TOOLCALL0000000000000007",
  tool: "some_future_tool",
  arguments: { region: "alps" },
  result: {
    headline: "Ride-out planner",
    stops: ["Stelvio", "Gavia"],
    durationDays: 3,
  },
  status: "succeeded",
  error: null,
};

/** Three chunks, two of which cite the same place — the de-dup case. */
export const kitchenSinkSources: MessageSource[] = [
  {
    chunkId: "01CHUNK00000000000000001",
    motorbikeId: "01BIKECB500F00000000000001",
    sourceDocumentId: "01SRCDOC0000000000000001",
    sourceUrl: "https://en.wikipedia.org/wiki/Honda_CB500F",
    sourceTitle: "Honda CB500F",
    headingPath: "Honda CB500F > Reception",
    score: 0.0328,
  },
  {
    chunkId: "01CHUNK00000000000000002",
    motorbikeId: "01BIKEMT07000000000000001",
    sourceDocumentId: "01SRCDOC0000000000000002",
    sourceUrl: "https://www.motorcyclenews.com/reviews/yamaha/mt-07/",
    sourceTitle: "Yamaha MT-07 (2021-) review",
    headingPath: null,
    score: 0.0211,
  },
  {
    // Same URL and heading path as the first one, through another document.
    chunkId: "01CHUNK00000000000000003",
    motorbikeId: "01BIKECB500F00000000000001",
    sourceDocumentId: "01SRCDOC0000000000000003",
    sourceUrl: "https://en.wikipedia.org/wiki/Honda_CB500F",
    sourceTitle: "Honda CB500F",
    headingPath: "Honda CB500F > Reception",
    score: 0.0164,
  },
];

export const kitchenSinkRecommendations: Recommendation[] = [
  {
    motorbikeId: "01BIKECB500F00000000000001",
    name: "Honda CB500F",
    imageUrl:
      "/media/motorbikes/01BIKECB500F00000000000001/01IMAGE00000000000000001_card.webp",
    rationale: "A2-legal, light and the lowest seat of the three.",
    matchedPreferences: ["budget", "a2"],
    keySpecs: {
      category: "naked",
      engineCc: 471,
      powerKw: 35.0,
      wetWeightKg: 189.0,
      seatHeightMm: 785,
      priceBand: "mid",
    },
  },
  {
    // No approved image at persist time — the fallback box keeps the height.
    motorbikeId: "01BIKEMT07000000000000001",
    name: "Yamaha MT-07",
    imageUrl: null,
    rationale: "More engine for later, if you restrict it for now.",
    matchedPreferences: ["riding_style"],
    keySpecs: {
      category: "naked",
      engineCc: 689,
      powerKw: 54.0,
      wetWeightKg: 184.0,
      seatHeightMm: null,
      priceBand: "mid",
    },
  },
];

const KITCHEN_SINK_BODY = `Based on what you told me, here is the shortlist.

- **Honda CB500F** — A2-legal as delivered.
- **Yamaha MT-07** — needs restricting.
`;

/**
 * The ui-spec §12 kitchen sink: all four styled tools, both subtle rows, one
 * unknown tool, three sources (one a duplicate) and two recommendations (one
 * without an image).
 */
export const kitchenSinkMessage: ChatMessage = {
  id: "01MESSAGE000000000000005",
  role: "assistant",
  body: KITCHEN_SINK_BODY,
  toolCalls: [
    catalogueSearchCall,
    specComparisonCall,
    licenceFitCheckCall,
    costEstimatorCall,
    recordPreferenceCall,
    flagUnknownBikeCall,
    unknownToolCall,
  ],
  sources: kitchenSinkSources,
  recommendations: kitchenSinkRecommendations,
  createdAt: "2026-08-26T14:02:00.000Z",
};
