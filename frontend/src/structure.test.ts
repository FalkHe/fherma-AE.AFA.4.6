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
  it("UI-33: lucide-react is the one allowed icon package; every other icon package is forbidden", () => {
    // step-0.1.md's original ban targets MUI's own icon package specifically
    // (it ships thousands of pre-styled SVGs the design system doesn't
    // control). Sprint 007/03's Goblin Pub theme then names `lucide-react`
    // as the one icon package this app is allowed to add, so the claim can
    // no longer be "no icon package at all" — it has to be "exactly this
    // one, nothing else". The two checks below still guard the original,
    // narrower ban directly (a dependency or import literally naming MUI's
    // icon package — spelled out below, not here, so this comment doesn't
    // itself trip the regex it's describing); the allow-list check after
    // them is what makes a *different* icon package (react-icons,
    // @heroicons/react, @ant-design/icons, …) fail too, which neither of
    // those two would catch on its own.
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

    // Allow-list: any dependency whose name reads as an icon package (the
    // "icon(s)" token, or "lucide" itself) must be exactly the one this
    // sprint approved. A stray second icon package added later would carry
    // one of these tokens in its name almost always (react-icons,
    // @heroicons/react, @ant-design/icons, @tabler/icons-react, …) and
    // would show up here even though it has nothing to do with MUI.
    const allowedIconPackages = ["lucide-react"];
    const looksLikeIconPackage = /icons?|lucide/i;
    const iconDependencies = Object.keys(allDeps).filter((name) => looksLikeIconPackage.test(name));
    expect(iconDependencies.sort()).toEqual([...allowedIconPackages].sort());
  });

  it("UI-34: no hex / rgb() / hsl() colour literal anywhere under src", () => {
    const hexOrFunctionColour = /#[0-9a-fA-F]{3,8}\b|(?:rgb|hsl)a?\(/;
    for (const file of listFilesRecursively(srcDir)) {
      if (!/\.(ts|tsx|json)$/.test(file) || !isNotATestFile(file)) continue;
      const content = fs.readFileSync(file, "utf8");
      expect(content, `${file} must not contain a colour literal`).not.toMatch(hexOrFunctionColour);
    }
  });

  it("AC1: no .css file outside src/core/theme/tokens/ holds a colour literal", () => {
    // UI-34 above is deliberately left untouched (its own scan is scoped to
    // `.ts|.tsx|.json` and never looks at `.css` — AC1 requires that rule to
    // keep passing exactly as it was written). But AC1 also says the design
    // system's token files are the *only* place a colour value is written,
    // and a `.css` file is exactly the kind of place a colour could leak
    // into without either of UI-34's checks ever seeing it. This is that
    // other half: every stylesheet under src, except the token files
    // themselves (`core/theme/tokens/*.css`, the one designated exception),
    // is held to the same hex/rgb()/hsl() ban.
    const hexOrFunctionColour = /#[0-9a-fA-F]{3,8}\b|(?:rgb|hsl)a?\(/;
    const tokensDir = path.join(srcDir, "core", "theme", "tokens");
    for (const file of listFilesRecursively(srcDir)) {
      if (!file.endsWith(".css")) continue;
      if (file.startsWith(tokensDir + path.sep)) continue;
      const content = fs.readFileSync(file, "utf8");
      expect(content, `${file} must not contain a colour literal — move it into core/theme/tokens/`).not.toMatch(
        hexOrFunctionColour,
      );
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

  it("UI-43: core/ holds exactly the pinned files, .tsx only under layout/, and none imports from modules/", () => {
    const coreDir = path.join(srcDir, "core");
    const expected = [
      // Pre-existing, unrelated to this sprint's theme work — kept as-is.
      "api/client.ts",
      "api/errors.ts",
      "i18n/index.ts",
      "i18n/i18n.d.ts",
      "i18n/locales/en/common.json",
      "i18n/locales/en/auth.json",
      // Sprint 007/05 WI1: the `/runs/:runId` screen's namespace — `run.*`
      // here (this work item), `party.*` added by WI2 in the same file;
      // sprint 007/07 WI1 added `dashboard.*` for the `/` screen once it
      // moved into this module too (the `home` module and its own
      // `home.json` are gone — see criterion 42(c) below).
      "i18n/locales/en/playthrough.json",
      // Sprint 009/06: the creation-chat page's own namespace — `chat.*`,
      // `choices.*`, `sheet.*`, `leave.*`.
      "i18n/locales/en/character.json",
      "queryClient.ts",
      // Sprint 007/03: the theme grew from a single `theme.ts` (removed)
      // into a directory, because AC1 needs somewhere to hold the design
      // system's token *stylesheets* — a single .ts file can't export CSS
      // custom properties. `theme/index.ts` is the same "build the MUI
      // theme object" module as before, just relocated; `theme/tokens.css`
      // is the aggregator `index.ts` imports, which in turn `@import`s the
      // seven per-category token files below — the actual, and only, place
      // a colour/font/spacing/motion value is written (AC1). The two test
      // files (`theme.test.ts`, `theme/index.test.ts`) cover the acceptance
      // criteria and the token-reference contract respectively; both live
      // under `core/` because the module they test does.
      "theme/index.ts",
      "theme/tokens.css",
      "theme/tokens/base.css",
      "theme/tokens/colors.css",
      "theme/tokens/fonts.css",
      "theme/tokens/motion.css",
      "theme/tokens/spacing.css",
      "theme/tokens/surfaces.css",
      "theme/tokens/typography.css",
      "theme.test.ts",
      "theme/index.test.ts",
      // Sprint 007/04: the guarded app frame used to be a `home` component
      // (`modules/home/components/AppShell.tsx`), but once `App.tsx` also
      // needed to render it — wrapping the signed-in routes from outside,
      // so the guard's pending/error states never flash a header — it had
      // two callers and neither one owned it, so it moved to `core/` like
      // any other twice-called module (AGENTS.md "a helper is promoted to
      // core/ only once a second module calls it, unchanged"). It stays a
      // component (not a hook or plain function), which is exactly why the
      // blanket "no .tsx under core/" ban below had to narrow rather than
      // just drop — this is the one legitimate exception, not a licence for
      // any component to land in `core/`.
      "layout/AppShell.tsx",
      "layout/AppShell.test.tsx",
    ].sort();

    const actual = listFilesRecursively(coreDir)
      .map((file) => path.relative(coreDir, file).split(path.sep).join("/"))
      .sort();

    expect(actual).toEqual(expected);

    const layoutDir = path.join(coreDir, "layout");
    for (const file of listFilesRecursively(coreDir)) {
      // `.tsx` anywhere else in `core/` would mean a component picked up a
      // module-shaped concern under the infrastructure tree instead of
      // living in the module that needs it — `layout/` is pinned above as
      // the one place that already earned the exception (see the comment
      // on `layout/AppShell.tsx`).
      if (file.endsWith(".tsx")) {
        expect(
          file.startsWith(layoutDir + path.sep),
          `${file} must not be a .tsx file — only core/layout/ may hold a component`,
        ).toBe(true);
      }
      // Widened to `.tsx` alongside `.ts`: `AppShell.tsx` is the first file
      // under `core/` that could actually reach into `modules/` (a plain
      // `.ts` scan would silently miss it), and the whole point of `core/`
      // is that it never depends downward on a module. Scoped to actual
      // `import` declaration lines, not the whole file, because
      // `layout/AppShell.test.tsx` legitimately *talks about* a
      // `modules/home/…` path in prose (explaining why it avoids a shared
      // test helper) without ever importing it — a whole-content scan would
      // fail that file for a sentence, not an import.
      if (file.endsWith(".ts") || file.endsWith(".tsx")) {
        const lines = fs.readFileSync(file, "utf8").split("\n");
        for (const line of lines) {
          if (!/^\s*import\b/.test(line)) continue;
          expect(line, `${file} must not import from src/modules/`).not.toMatch(/modules\//);
        }
      }
    }
  });

  it("criterion 42(a): src/components/ does not exist, or exists empty of .ts/.tsx files", () => {
    const componentsDir = path.join(srcDir, "components");
    const tsFiles = listFilesRecursively(componentsDir).filter((file) => /\.(ts|tsx)$/.test(file));
    expect(tsFiles).toEqual([]);
  });

  it("criterion 42(b): AppShell.tsx lives at core/layout/ and imports nothing from any module", () => {
    // Retargeted from `modules/home/components/` (sprint 007/04 WI2): the
    // frame now has two callers — `App.tsx` and, previously, `home`'s own
    // routes — so it moved to `core/`, the one place either side may import
    // from without creating a module-to-module edge (see the `layout/`
    // comment on the UI-43 pin list above).
    const appShellPath = path.join(srcDir, "core", "layout", "AppShell.tsx");
    const content = fs.readFileSync(appShellPath, "utf8");
    const importLines = content.split("\n").filter((line) => /^\s*import\b/.test(line));
    for (const line of importLines) {
      expect(line, "AppShell.tsx must not import from any module").not.toMatch(/modules\//);
    }
  });

  it("criterion 42(c): the one permitted cross-module import is playthrough -> auth's useCurrentUser, never the reverse", () => {
    // Retargeted from `home` to `playthrough` (sprint 007/07 WI1, AC6): the
    // `home` module is gone entirely, and its one cross-module edge —
    // reading `useCurrentUser` for the greeting — moved with `HomeRoute`'s
    // replacement, `DashboardRoute`, into `playthrough`. Scoped to actual
    // `import … from "…/auth/…"` / `"…/playthrough/…"` declaration lines,
    // not every line containing the substring "auth/" or "playthrough/" —
    // that substring also occurs in API route path literals
    // (`"/api/v1/auth/sign-out"`, `"/api/v1/playthrough/runs"`) and in this
    // suite's own cross-referencing comments, neither of which is a module
    // import and both of which are false positives for this criterion under
    // the wider scan.
    //
    // `SignOutButton` and `useSignOut` stay off the allow-list: sign-out
    // lives entirely in `auth`'s own `AccountMenu`, which owns `useSignOut`
    // itself, so `playthrough` has no reason to reach for either — keeping
    // them allowed would hide a real regression if it ever imported
    // sign-out machinery instead of just the current user it needs for the
    // greeting.
    const allowedNames = ["useCurrentUser"];
    const playthroughDir = path.join(srcDir, "modules", "playthrough");
    const authDir = path.join(srcDir, "modules", "auth");
    const importFromAuth = /^\s*import\b.*["'][^"']*auth\/[^"']*["']/;
    const importFromPlaythrough = /^\s*import\b.*["'][^"']*playthrough\/[^"']*["']/;

    for (const file of listFilesRecursively(playthroughDir)) {
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
        expect(importFromPlaythrough.test(line), `${file}: "${line.trim()}" must not import from modules/playthrough`).toBe(
          false,
        );
      }
    }

    expect(fs.existsSync(path.join(authDir, "api.ts"))).toBe(false);
    expect(fs.existsSync(path.join(authDir, "components", "SignOutButton.tsx"))).toBe(false);

    // AC6: the old landing module is gone outright, not just unregistered.
    expect(fs.existsSync(path.join(srcDir, "modules", "home"))).toBe(false);
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
