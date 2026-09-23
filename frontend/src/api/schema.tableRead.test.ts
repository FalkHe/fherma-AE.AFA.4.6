// qa acceptance test -- sprint 010/05 "table read" (WI2)
// (docs/intents/010-dm-agent-in-gui/sprints/05-table-read/), the regenerated
// typed client half: "schema.d.ts regenerated and committed".
//
// Static and file-level, the same pattern `schema.runReads.test.ts` already
// pins for sprint 007/02's own run reads: it reads the committed
// `schema.d.ts` as text and asserts (a) the new path is present and mapped
// to a GET operation, and (b) the three new wire shapes (`TableRead`,
// `TableAdventure`, `TableScene`) appear with exactly their field set. It
// never runs `openapi-typescript` itself (a build step, not a unit test)
// and never imports the generated types, so a currently-missing path or
// shape fails the assertion cleanly instead of a TypeScript compile error.
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const apiDir = path.dirname(fileURLToPath(import.meta.url));
const schemaPath = path.join(apiDir, "schema.d.ts");

function readSchema(): string {
  return fs.readFileSync(schemaPath, "utf8");
}

// The exact, currently-committed field sets (I1's `TableRead`/
// `TableAdventure`/`TableScene`, `playthrough/schemas.py`) -- untouched
// means every caller built against this sprint still compiles.
const TABLE_READ_SHAPE = `        TableRead: {
            /** Runid */
            runId: string;
            /** Runtitle */
            runTitle: string | null;
            /** Runstatus */
            runStatus: string;
            /** Campaigntitle */
            campaignTitle: string | null;
            adventure: components["schemas"]["TableAdventure"] | null;
            scene: components["schemas"]["TableScene"] | null;
            /** Heroes */
            heroes: components["schemas"]["CharacterRead"][];
        };`;

const TABLE_ADVENTURE_SHAPE = `        TableAdventure: {
            /** Id */
            id: string;
            /** Runid */
            runId: string;
            /** Title */
            title: string;
            /**
             * Status
             * @enum {string}
             */
            status: "active" | "completed";
        };`;

const TABLE_SCENE_SHAPE = `        TableScene: {
            /** Id */
            id: string;
            /** Name */
            name: string;
        };`;

function pathBlock(schema: string, pathLiteral: string): string {
  const marker = `"${pathLiteral}": {`;
  const start = schema.indexOf(marker);
  expect(start, `${pathLiteral} must be a key of components["paths"] in schema.d.ts`).toBeGreaterThan(-1);
  const end = schema.indexOf("\n    };", start);
  return schema.slice(start, end);
}

describe("table read schema", () => {
  it("schema.d.ts carries the table-read path and its three wire shapes", () => {
    const schema = readSchema();

    const tableBlock = pathBlock(schema, "/api/v1/playthrough/runs/{run_id}/table");
    expect(tableBlock).toMatch(/get: operations\[/);

    expect(schema).toContain(TABLE_READ_SHAPE);
    expect(schema).toContain(TABLE_ADVENTURE_SHAPE);
    expect(schema).toContain(TABLE_SCENE_SHAPE);
  });
});
