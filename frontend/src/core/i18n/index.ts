// i18next init, English resources only (step-0.1.md §6.2, D13). One
// namespace per frontend module plus `common`; `defaultNS` is `common`.
import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import common from "./locales/en/common.json";
import auth from "./locales/en/auth.json";
import home from "./locales/en/home.json";
import playthrough from "./locales/en/playthrough.json";

export const resources = {
  en: { common, auth, home, playthrough },
} as const;

void i18next.use(initReactI18next).init({
  resources,
  lng: "en",
  fallbackLng: "en",
  defaultNS: "common",
  interpolation: { escapeValue: false },
});

export default i18next;
