// Compile-checked keys: a `t()` call for a key that does not exist in the
// English resources fails `pnpm typecheck` (step-0.1.md §6.2, UI-32).
import "i18next";

import type { resources } from "./index";

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "common";
    resources: (typeof resources)["en"];
  }
}
