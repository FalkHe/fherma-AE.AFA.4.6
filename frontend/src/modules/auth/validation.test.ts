// Covers UI-15's numeric half: the rule numbers live in exactly one place
// (ui-spec.md §4, step-0.1.md §6.4 OQ-2/OQ-3) and everything else —
// including the translation JSON — interpolates them. Component-level
// behaviour (timing, message-per-field, focus) is covered where the rules
// are actually applied: SignUpRoute.test.tsx and SignInRoute.test.tsx. This
// file intentionally does not guess at a validator function's name or
// signature beyond the constants step-0.1.md §6.4 pins.
import { describe, expect, it } from "vitest";

import { PASSWORD_MAX, PASSWORD_MIN, USERNAME_MAX, USERNAME_MIN, USERNAME_PATTERN } from "./validation";

describe("modules/auth/validation", () => {
  it("pins the username rule numbers from step-0.1.md §6.4 OQ-2", () => {
    expect(USERNAME_MIN).toBe(3);
    expect(USERNAME_MAX).toBe(32);
  });

  it("pins the password rule numbers from step-0.1.md §6.4 OQ-3", () => {
    expect(PASSWORD_MIN).toBe(8);
    expect(PASSWORD_MAX).toBe(128);
  });

  it("accepts letters, digits, underscore and hyphen and nothing else", () => {
    expect(USERNAME_PATTERN.test("thorin_42-oakenshield")).toBe(true);
    expect(USERNAME_PATTERN.test("thorin oakenshield")).toBe(false); // space
    expect(USERNAME_PATTERN.test("thorin.oakenshield")).toBe(false); // dot
    expect(USERNAME_PATTERN.test("thörin")).toBe(false); // non-ASCII letter
  });
});
