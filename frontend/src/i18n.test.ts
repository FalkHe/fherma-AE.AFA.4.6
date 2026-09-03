import { describe, expect, it } from "vitest";

import { i18n } from "./i18n";
import { themeModes } from "./theme";

describe("translation catalogue", () => {
  it("initialises synchronously with the English catalogue", () => {
    expect(i18n.isInitialized).toBe(true);
    expect(i18n.t("app.name")).toBe("Motorcycle Buying Advisor");
  });

  it("labels every theme mode the toggle can offer", () => {
    for (const themeMode of themeModes) {
      const key = `themeMode.${themeMode}` as const;

      // A missing key makes i18next echo the key itself, which would reach the
      // UI as raw "themeMode.dark" text.
      expect(i18n.t(key)).not.toBe(key);
    }
  });
});
