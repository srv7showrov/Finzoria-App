import { useState } from "react";
import { LanguageSelect } from "../components/inputs";
import assistantPortrait from "../assets/assistant-portrait.webp";
import { Icon } from "../components/icons";
import { Logo } from "../components/Logo";
import { Notice } from "../components/ui";
import { isLocale, useI18n, type Locale } from "../i18n";
import type { Section } from "../router";

export function Landing({
  locale,
  onLocaleChange,
  onStart,
}: {
  locale: Locale;
  onLocaleChange: (locale: Locale) => void;
  onStart: (target: "settings" | Section) => Promise<void>;
}) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  const go = async (target: "settings" | Section) => {
    setBusy(true);
    setError(false);
    try {
      await onStart(target);
    } catch {
      setError(true);
      setBusy(false);
    }
  };

  return (
    <div className="landing">
      <header className="landing-top">
        <Logo name={t("app.name")} tagline={t("app.tagline")} />
        <div className="landing-language">
          <LanguageSelect label={t("landing.languageLabel")} value={locale} onChange={(v) => isLocale(v) && onLocaleChange(v)} />
        </div>
      </header>
      <main className="hero">
        <div className="hero-text">
          <span className="demo-pill">
            <span className="demo-dot" aria-hidden="true" />
            {t("top.demo")}
          </span>
          <h1>{t("landing.hero")}</h1>
          <p className="hero-copy">{t("landing.copy")}</p>
          <ul className="hero-points">
            {(["landing.point1", "landing.point2", "landing.point3"] as const).map((k) => (
              <li key={k}>
                <Icon name="checkCircle" size={20} />
                {t(k)}
              </li>
            ))}
          </ul>
          <div className="hero-actions">
            <button type="button" className="btn btn-primary btn-large" disabled={busy} onClick={() => go("settings")}>
              {t("landing.start")}
            </button>
            <button type="button" className="btn btn-secondary btn-large" disabled={busy} onClick={() => go("dashboard")}>
              {t("landing.explore")}
            </button>
          </div>
          {busy && <p role="status">{t("landing.starting")}</p>}
          {error && <Notice tone="danger">{t("error.network")}</Notice>}
          <p className="muted">{t("landing.note")}</p>
        </div>
        <div className="hero-art" aria-hidden="true">
          <img src={assistantPortrait} alt="" width={520} height={435} />
        </div>
      </main>
      <footer className="footer">{t("footer.disclaimer")}</footer>
    </div>
  );
}
