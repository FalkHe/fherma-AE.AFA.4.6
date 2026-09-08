// The rule constants and nothing else is hard-coded elsewhere: the numbers
// come from step-0.1.md §6.4 OQ-2/OQ-3 and are interpolated into copy, so no
// translation string ever contains a number (ui-spec.md §4).
import type { TFunction } from "i18next";

export const USERNAME_MIN = 3;
export const USERNAME_MAX = 32;
export const USERNAME_PATTERN = /^[A-Za-z0-9_-]+$/;

export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 128;

/** A field validation failure: the i18n key (within the `auth` namespace) plus any interpolation values. */
export interface FieldValidationError {
  key: string;
  values?: Record<string, number>;
}

/**
 * Resolves a `FieldValidationError` (or a server-mapped field error, e.g. the
 * 409 username-taken case) through the `auth` namespace. The cast is
 * necessary because the key is computed at runtime while `t()`'s generated
 * type only accepts the namespace's literal key union.
 */
export function translateFieldError(t: TFunction<"auth">, error: FieldValidationError): string {
  // The key is computed at runtime; `t()`'s generated type only accepts the
  // namespace's literal key union, which a dynamic string cannot satisfy
  // structurally.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return t(error.key as any, error.values);
}

/** Sign-in validates presence only (ui-spec.md §4): applying length/charset rules here would leak account-format information to an attacker. */
export function validateUsernameRequired(value: string): FieldValidationError | null {
  return value.trim().length === 0 ? { key: "validation.username.required" } : null;
}

export function validatePasswordRequired(value: string): FieldValidationError | null {
  return value.length === 0 ? { key: "validation.password.required" } : null;
}

/** Sign-up applies the full rule set, in order; the first failure is shown (ui-spec.md §4). */
export function validateUsernameFull(value: string): FieldValidationError | null {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return { key: "validation.username.required" };
  }
  if (trimmed.length < USERNAME_MIN) {
    return { key: "validation.username.tooShort", values: { min: USERNAME_MIN } };
  }
  if (trimmed.length > USERNAME_MAX) {
    return { key: "validation.username.tooLong", values: { max: USERNAME_MAX } };
  }
  if (!USERNAME_PATTERN.test(trimmed)) {
    return { key: "validation.username.charset" };
  }
  return null;
}

export function validatePasswordFull(value: string): FieldValidationError | null {
  if (value.length === 0) {
    return { key: "validation.password.required" };
  }
  if (value.length < PASSWORD_MIN) {
    return { key: "validation.password.tooShort", values: { min: PASSWORD_MIN } };
  }
  if (value.length > PASSWORD_MAX) {
    return { key: "validation.password.tooLong", values: { max: PASSWORD_MAX } };
  }
  return null;
}
