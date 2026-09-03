import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en/translation.json";

export const defaultNS = "translation";

/**
 * English is the only catalogue for now, but every user-facing string goes
 * through i18next from the start so that adding a locale later is translation
 * work rather than a refactor.
 *
 * Catalogues are imported statically and `init` therefore resolves
 * synchronously: the app shell paints real strings immediately and needs no
 * Suspense boundary. A future locale added via a backend/HTTP catalogue is the
 * point at which that changes.
 */
export const i18n = i18next.use(initReactI18next);

void i18n.init({
  lng: "en",
  fallbackLng: "en",
  defaultNS,
  resources: {
    en: { translation: en },
  },
  interpolation: {
    // React escapes interpolated values already.
    escapeValue: false,
  },
});

/**
 * Makes `t("...")` keys compile-time checked against the English catalogue,
 * so a typo is a type error instead of a raw key rendered in the UI.
 */
declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: typeof defaultNS;
    resources: { translation: typeof en };
  }
}
