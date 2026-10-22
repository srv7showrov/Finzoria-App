import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import { ar } from "./ar";
import { bn } from "./bn";
import { de } from "./de";
import { en } from "./en";
import { hi } from "./hi";
import type { MessageKey, Messages } from "./types";
import { zhHans } from "./zh-Hans";

export type Locale = "en" | "zh-Hans" | "bn" | "hi" | "ar" | "de";

export const LOCALES: ReadonlyArray<{ code: Locale; nativeName: string; dir: "ltr" | "rtl" }> = [
  { code: "en", nativeName: "English", dir: "ltr" },
  { code: "zh-Hans", nativeName: "简体中文", dir: "ltr" },
  { code: "bn", nativeName: "বাংলা", dir: "ltr" },
  { code: "hi", nativeName: "हिन्दी", dir: "ltr" },
  { code: "ar", nativeName: "العربية", dir: "rtl" },
  { code: "de", nativeName: "Deutsch", dir: "ltr" },
];

const CATALOGS: Record<Locale, Messages> = { en, "zh-Hans": zhHans, bn, hi, ar, de };

export function isLocale(value: string): value is Locale {
  return value in CATALOGS;
}

export interface I18n {
  locale: Locale;
  dir: "ltr" | "rtl";
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
  formatMoney: (amount: string, currency: string) => string;
  formatDate: (isoDate: string) => string;
  /** UTC instant shown in the workspace's IANA time zone, with the zone name. */
  formatDateTime: (isoInstant: string) => string;
  timeZone: string;
}

const I18nContext = createContext<I18n | null>(null);

export function I18nProvider({ locale, timeZone, children }: { locale: Locale; timeZone?: string; children: ReactNode }) {
  const zone = timeZone || Intl.DateTimeFormat().resolvedOptions().timeZone;
  const value = useMemo<I18n>(() => {
    const catalog = CATALOGS[locale];
    const dir = LOCALES.find((l) => l.code === locale)?.dir ?? "ltr";
    return {
      locale,
      dir,
      t: (key, vars) => {
        const template = catalog[key] ?? en[key] ?? key;
        return vars ? template.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`)) : template;
      },
      // Amounts stay decimal strings; Intl formats the string without converting to a binary float.
      // The ISO code is always shown so currencies are never confused ("$" could be USD or AUD).
      formatMoney: (amount, currency) =>
        new Intl.NumberFormat(locale, { style: "currency", currency, currencyDisplay: "code" }).format(amount as `${number}`),
      // Date-only values are formatted in UTC so they never shift by a day across time zones.
      formatDate: (isoDate) => {
        const [y, m, d] = isoDate.split("-").map(Number);
        if (!y || !m || !d) return isoDate;
        return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeZone: "UTC" }).format(
          new Date(Date.UTC(y, m - 1, d)),
        );
      },
      formatDateTime: (isoInstant) =>
        // dateStyle/timeStyle cannot be combined with timeZoneName, so list the fields explicitly.
        new Intl.DateTimeFormat(locale, {
          year: "numeric",
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: zone,
          timeZoneName: "short",
        }).format(new Date(isoInstant)),
      timeZone: zone,
    };
  }, [locale, zone]);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = value.dir;
  }, [locale, value.dir]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}
