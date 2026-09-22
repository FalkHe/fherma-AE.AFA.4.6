// qa acceptance test -- sprint 007/02 "run reads for the screens"
// (docs/intents/007-initial-frontend/sprints/02-run-reads-for-screens/brief.md),
// AC5 only: "schema.d.ts regenerated and committed; the existing run schema
// is untouched, so every earlier caller still compiles."
//
// Static and file-level, exactly the kind `structure.test.ts` already uses
// for other generated/committed-file claims: it reads the committed
// `schema.d.ts` as text and asserts (a) both new paths (I1) are present and
// mapped to a GET operation, and (b) the existing `CampaignRunRead` schema
// component -- the shape sprint 005 and every earlier caller compile
// against -- appears byte-for-byte unchanged. It never runs `openapi-typescript`
// itself (that belongs to `make generate-api`, a build step, not a unit
// test -- see `structure.test.ts`'s own note on criterion 44) and it never
// imports the generated types, so a currently-missing path fails the
// assertion cleanly instead of a TypeScript compile error.
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const apiDir = path.dirname(fileURLToPath(import.meta.url));
const schemaPath = path.join(apiDir, "schema.d.ts");

function readSchema(): string {
  return fs.readFileSync(schemaPath, "utf8");
}

// The exact, currently-committed `CampaignRunRead` component (I2's "the
// existing run schema", `playthrough/schemas.py`'s six fields) -- untouched
// means this literal block still appears verbatim.
const EXISTING_CAMPAIGN_RUN_READ_SHAPE = `        CampaignRunRead: {
            /** Id */
            id: string;
            /** Campaignid */
            campaignId: string;
            /** Contentversion */
            contentVersion: string;
            /** Title */
            title: string | null;
            /** Status */
            status: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };`;

function pathBlock(schema: string, pathLiteral: string): string {
  const marker = `"${pathLiteral}": {`;
  const start = schema.indexOf(marker);
  expect(start, `${pathLiteral} must be a key of components["paths"] in schema.d.ts`).toBeGreaterThan(-1);
  const end = schema.indexOf("\n    };", start);
  return schema.slice(start, end);
}

describe("AC5", () => {
  it("AC5: schema.d.ts carries both new run-read paths and the existing run schema untouched", () => {
    const schema = readSchema();

    const listBlock = pathBlock(schema, "/api/v1/playthrough/runs");
    expect(listBlock).toMatch(/get: operations\[/);

    const overviewBlock = pathBlock(schema, "/api/v1/playthrough/runs/{run_id}/overview");
    expect(overviewBlock).toMatch(/get: operations\[/);

    // The existing run schema, untouched -- every earlier caller still
    // compiles against it.
    expect(schema).toContain(EXISTING_CAMPAIGN_RUN_READ_SHAPE);
  });
});
