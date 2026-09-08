// The repo-structure and module-boundary criteria (ui-spec.md UI-33, UI-34,
// UI-40, UI-43; step-0.1.md §8 criteria 42, 43) read as static facts about
// the tree rather than rendered behaviour, so they are asserted directly
// against the filesystem instead of being guessed at through a component
// render. Every check below reads real files and therefore fails loudly
// (ENOENT) until frontend-dev lands them — that is the expected state this
// round (mode A).
//
// Two criteria this file deliberately does NOT attempt, and why:
//   - UI-31/UI-41's "no user-facing string literal in a component" half is a
//     static-source claim that a regex cannot check without a very high
//     false-positive rate (it would need to parse JSX to tell a literal prop
//     value from a translated string). The *rendered* half — no raw key path
//     ever reaches the screen — is covered indirectly and strongly by every
//     other suite in this tree: each of them asserts the exact translated
//     copy from ui-spec.md §7, so an unresolved key (which i18next renders as
//     the key itself) would fail nearly every test in the tree, not just this
//     file. See the qa-frontend report for the full reasoning.
//   - Criterion 44 (`schema.d.ts` byte-identical to a fresh `pnpm
//     generate:api`) needs the `openapi-typescript` CLI and a Node toolchain
//     invocation, which is a build-verification step, not a unit test; it
//     belongs to the `make generate-api` + `git diff` check the qa-checklist
//     skill and step-0.1.md §7 already prescribe for mode B.
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const srcDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(srcDir, "..");

function readJson(relativePath: string): unknown {
  return JSON.parse(fs.readFileSync(path.join(frontendDir, relativePath), "utf8"));
}

function listFilesRecursively(dir: string): string[] {
  if (!fs.existsSync(dir)) {
    return [];
  }
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      return listFilesRecursively(full);
    }
    return [full];
  });
}

// UI-34 and UI-40 are claims about the *application* source (the thing that
// ships), not about qa-frontend's own test prose. A `.test.ts(x)` file's
// `describe`/`it` names are English sentences describing what a criterion
// forbids — e.g. this very file's own `"UI-34: no hex / rgb() / hsl() colour
// literal …"` title contains the literal substring "rgb(" — and scanning them
// with the same regex the criterion is about produces a false positive
// against the test suite, not a real defect in `src/{modules,core}`. Excluded
// here for that reason; every other structural check in this file (UI-33,
// UI-43, criteria 42/43) still scans every file, `.test.ts(x)` included,
// because those checks are import-graph and file-tree facts a test file could
// still genuinely violate.
function isNotATestFile(file: string): boolean {
  return !/\.test\.(ts|tsx)$/.test(file);
}

// Built from parts so that a later plain-text `grep -r` for these terms
// under `frontend/src` does not match this file's own source — the terms
// only ever exist here as runtime-assembled strings, never as a literal
// contiguous token (UI-40's own wording: "grepping frontend/src finds no
// occurrence").
const forbiddenStorageTerms = ["local" + "Storage", "session" + "Storage", "document" + "." + "cookie"];

describe("Repo structure (UI-33, UI-34, UI-40, UI-43, criteria 42/43)", () => {
  it("UI-33: no icon package is a dependency, and no component imports one", () => {
    const packageJson = readJson("package.json") as {
      dependencies?: Record<string, string>;
      devDependencies?: Record<string, string>;
    };
    const allDeps = { ...packageJson.dependencies, ...packageJson.devDependencies };
    for (const name of Object.keys(allDeps)) {
      expect(name).not.toMatch(/icons?-material/i);
    }

    for (const file of listFilesRecursively(srcDir)) {
      if (!/\.(ts|tsx)$/.test(file)) continue;
      const content = fs.readFileSync(file, "utf8");
      expect(content, `${file} must not import an icon package`).not.toMatch(/@mui\/icons-material/);
    }
  });

  it("UI-34: no hex / rgb() / hsl() colour literal anywhere under src", () => {
    const hexOrFunctionColour = /#[0-9a-fA-F]{3,8}\b|(?:rgb|hsl)a?\(/;
    for (const file of listFilesRecursively(srcDir)) {
      if (!/\.(ts|tsx|json)$/.test(file) || !isNotATestFile(file)) continue;
      const content = fs.readFileSync(file, "utf8");
      expect(content, `${file} must not contain a colour literal`).not.toMatch(hexOrFunctionColour);
    }
  });

  it("UI-40: nothing under src reads or writes document.cookie, localStorage or sessionStorage", () => {
    for (const file of listFilesRecursively(srcDir)) {
      if (!/\.(ts|tsx)$/.test(file) || !isNotATestFile(file)) continue;
      const content = fs.readFileSync(file, "utf8");
      for (const term of forbiddenStorageTerms) {
        expect(content, `${file} must not reference ${term}`).not.toContain(term);
      }
    }
  });

  it("UI-43: core/ holds exactly the pinned files, none of them .tsx, and none imports from modules/", () => {
    const coreDir = path.join(srcDir, "core");
    const expected = [
      "api/client.ts",
      "api/errors.ts",
      "i18n/index.ts",
      "i18n/i18n.d.ts",
      "i18n/locales/en/common.json",
      "i18n/locales/en/auth.json",
      "i18n/locales/en/home.json",
      "queryClient.ts",
      "theme.ts",
    ].sort();

    const actual = listFilesRecursively(coreDir)
      .map((file) => path.relative(coreDir, file).split(path.sep).join("/"))
      .sort();

    expect(actual).toEqual(expected);

    for (const file of listFilesRecursively(coreDir)) {
      expect(file.endsWith(".tsx"), `${file} must not be a .tsx file — core/ is infrastructure only`).toBe(false);
      if (file.endsWith(".ts")) {
        const content = fs.readFileSync(file, "utf8");
        expect(content, `${file} must not import from src/modules/`).not.toMatch(/modules\//);
      }
    }
  });

  it("criterion 42(a): src/components/ does not exist, or exists empty of .ts/.tsx files", () => {
    const componentsDir = path.join(srcDir, "components");
    const tsFiles = listFilesRecursively(componentsDir).filter((file) => /\.(ts|tsx)$/.test(file));
    expect(tsFiles).toEqual([]);
  });

  it("criterion 42(b): AppShell.tsx lives at modules/home/components/ and imports nothing from any module", () => {
    const appShellPath = path.join(srcDir, "modules", "home", "components", "AppShell.tsx");
    const content = fs.readFileSync(appShellPath, "utf8");
    const importLines = content.split("\n").filter((line) => /^\s*import\b/.test(line));
    for (const line of importLines) {
      expect(line, "AppShell.tsx must not import from any module").not.toMatch(/modules\//);
    }
  });

  it("criterion 42(c): the one permitted cross-module import is home -> auth's SignOutButton/useSignOut/useCurrentUser, never the reverse", () => {
    // Scoped to actual `import … from "…/auth/…"` / `"…/home/…"` declaration
    // lines, not every line containing the substring "auth/" or "home/" —
    // that substring also occurs in API route path literals
    // (`"/api/v1/auth/sign-out"`) and in this suite's own cross-referencing
    // comments (`// modules/auth/csrf.test.tsx, next to …`), neither of which
    // is a module import and both of which are false positives for this
    // criterion under the wider scan.
    const allowedNames = ["SignOutButton", "useSignOut", "useCurrentUser"];
    const homeDir = path.join(srcDir, "modules", "home");
    const authDir = path.join(srcDir, "modules", "auth");
    const importFromAuth = /^\s*import\b.*["'][^"']*auth\/[^"']*["']/;
    const importFromHome = /^\s*import\b.*["'][^"']*home\/[^"']*["']/;

    for (const file of listFilesRecursively(homeDir)) {
      if (!/\.(ts|tsx)$/.test(file)) continue;
      const lines = fs.readFileSync(file, "utf8").split("\n");
      for (const line of lines) {
        if (!importFromAuth.test(line)) continue;
        const referencesAllowedName = allowedNames.some((name) => line.includes(name));
        expect(referencesAllowedName, `${file}: "${line.trim()}" must reference only ${allowedNames.join(", ")}`).toBe(
          true,
        );
      }
    }

    for (const file of listFilesRecursively(authDir)) {
      if (!/\.(ts|tsx)$/.test(file)) continue;
      const lines = fs.readFileSync(file, "utf8").split("\n");
      for (const line of lines) {
        expect(importFromHome.test(line), `${file}: "${line.trim()}" must not import from modules/home`).toBe(false);
      }
    }

    expect(fs.existsSync(path.join(authDir, "api.ts"))).toBe(false);
  });

  it("UI-15's JSON half: the rule numbers never appear literally in auth.json — only {{min}}/{{max}} placeholders do", () => {
    const authJson = readJson("src/core/i18n/locales/en/auth.json") as {
      fields: { username: { hint: string }; password: { hint: string } };
      validation: {
        username: { tooShort: string; tooLong: string };
        password: { tooShort: string; tooLong: string };
      };
    };
    const interpolatedStrings = [
      authJson.fields.username.hint,
      authJson.fields.password.hint,
      authJson.validation.username.tooShort,
      authJson.validation.username.tooLong,
      authJson.validation.password.tooShort,
      authJson.validation.password.tooLong,
    ];
    for (const value of interpolatedStrings) {
      expect(value, `"${value}" must not hard-code a rule number`).not.toMatch(/\d/);
    }
  });
});
