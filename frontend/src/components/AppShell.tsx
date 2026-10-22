import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, type Preferences } from "../api";
import { LOCALES, useI18n } from "../i18n";
import type { MessageKey } from "../i18n/types";
import { CURRENCIES } from "../money";
import { SECTIONS, hrefFor, navigate, type Route, type Section } from "../router";
import { AssistantPanel } from "./AssistantPanel";
import { Icon, type IconName } from "./icons";
import { Logo } from "./Logo";

const NAV_ICONS: Record<Section, IconName> = {
  dashboard: "home",
  workspace: "sparkle",
  payments: "card",
  currency: "globe",
  budget: "chart",
  funding: "cap",
  trust: "shield",
  reports: "doc",
};

interface ShellContextValue {
  openAssistant: () => void;
  /** Top-bar slot where a page may render a control that drives its own view (the dashboard period). */
  topbarSlot: HTMLElement | null;
}

const ShellContext = createContext<ShellContextValue>({ openAssistant: () => undefined, topbarSlot: null });

export function useShell(): ShellContextValue {
  return useContext(ShellContext);
}

function NavLink({ route, current, label, icon, onNavigate }: { route: Route; current: boolean; label: string; icon: IconName; onNavigate: () => void }) {
  return (
    <a
      href={hrefFor(route)}
      className="nav-link"
      aria-current={current ? "page" : undefined}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        navigate(route);
        onNavigate();
      }}
    >
      <Icon name={icon} size={22} />
      <span>{label}</span>
    </a>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts;
  return letters.map((p) => Array.from(p ?? "")[0] ?? "").join("").toUpperCase();
}

/** Language and display-currency controls save the workspace preferences (same API as Settings). */
function PreferenceControls({ preferences, onSaved }: { preferences: Preferences; onSaved: (p: Preferences) => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const save = async (change: Partial<Pick<Preferences, "language" | "display_currency">>) => {
    setBusy(true);
    setFailed(false);
    try {
      onSaved(await api.savePreferences({ ...preferences, ...change }));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <label className="top-select">
        <Icon name="language" size={20} />
        <span className="sr-only">{t("settings.language")}</span>
        <select value={preferences.language} disabled={busy} onChange={(e) => save({ language: e.target.value })}>
          {LOCALES.map((l) => (
            <option key={l.code} value={l.code} lang={l.code}>
              {l.nativeName}
            </option>
          ))}
        </select>
        <Icon name="chevronDown" size={16} className="top-select-chevron" />
      </label>
      <label className="top-select">
        <Icon name="coins" size={20} />
        <span className="sr-only">{t("top.currency")}</span>
        <select value={preferences.display_currency} disabled={busy} onChange={(e) => save({ display_currency: e.target.value })}>
          {CURRENCIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <Icon name="chevronDown" size={16} className="top-select-chevron" />
      </label>
      {failed && (
        <p className="top-error" role="alert">
          {t("top.saveFailed")}
        </p>
      )}
    </>
  );
}

export function AppShell({
  route,
  preferences,
  onPreferencesSaved,
  children,
}: {
  route: Route;
  preferences: Preferences;
  onPreferencesSaved: (p: Preferences) => void;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const [menuOpen, setMenuOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [topbarSlot, setTopbarSlot] = useState<HTMLElement | null>(null);
  const [profileName, setProfileName] = useState<string | null>(null);
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpen(false);
        setAssistantOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Move focus to the new page heading after navigation so keyboard users keep their place.
  useEffect(() => {
    mainRef.current?.querySelector<HTMLElement>("h1")?.focus();
  }, [route]);

  // A link with a hash (for example from Learn More) moves focus to that card once it has
  // rendered. Cards may appear after data loads, so the target is looked up for a short while.
  useEffect(() => {
    let timer = 0;
    const seek = (attempt: number) => {
      const id = decodeURIComponent(window.location.hash.slice(1));
      if (!id) return;
      const el = document.getElementById(id);
      const closed = el?.closest("details:not([open])");
      if (closed instanceof HTMLDetailsElement) closed.open = true;
      if (el && !el.closest("[hidden]") && el.tabIndex >= -1 && el.tagName !== "BUTTON") {
        el.scrollIntoView({ block: "start" });
        el.focus({ preventScroll: true });
        return;
      }
      if (attempt < 30) timer = window.setTimeout(() => seek(attempt + 1), 100);
    };
    const start = () => {
      window.clearTimeout(timer);
      seek(0);
    };
    start();
    window.addEventListener("popstate", start);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("popstate", start);
    };
  }, [route]);

  // The profile name can change in Settings, so it is re-read after navigation.
  useEffect(() => {
    let cancelled = false;
    api.profile().then(
      (p) => !cancelled && setProfileName(p.display_name),
      () => !cancelled && setProfileName(null),
    );
    return () => {
      cancelled = true;
    };
  }, [route]);

  const closeMenu = () => setMenuOpen(false);

  return (
    <ShellContext.Provider value={{ openAssistant: () => setAssistantOpen(true), topbarSlot }}>
      <div className={`shell${assistantOpen ? " assistant-open" : ""}`}>
        <a className="skip-link" href="#main">
          {t("app.skipToContent")}
        </a>
        <aside className="sidebar">
          <div className="sidebar-brand">
            <a
              className="brand"
              href="/"
              onClick={(e) => {
                e.preventDefault();
                navigate({ page: "landing" });
              }}
            >
              <Logo name={t("app.name")} tagline={t("app.tagline")} />
            </a>
            <button
              type="button"
              className="menu-button"
              aria-expanded={menuOpen}
              aria-controls="sidebar"
              onClick={() => setMenuOpen((v) => !v)}
            >
              <Icon name={menuOpen ? "close" : "menu"} size={22} />
              <span>{menuOpen ? t("nav.closeMenu") : t("nav.menu")}</span>
            </button>
          </div>
          <nav id="sidebar" className={`nav${menuOpen ? " open" : ""}`} aria-label={t("nav.main")}>
            <ul>
              {SECTIONS.map((section) => (
                <li key={section}>
                  <NavLink
                    route={{ page: "section", section }}
                    current={route.page === "section" && route.section === section}
                    label={t(`nav.short.${section}` as MessageKey)}
                    icon={NAV_ICONS[section]}
                    onNavigate={closeMenu}
                  />
                </li>
              ))}
            </ul>
            <ul className="nav-secondary">
              <li>
                <NavLink route={{ page: "learn" }} current={route.page === "learn"} label={t("nav.learn")} icon="book" onNavigate={closeMenu} />
              </li>
              <li>
                <NavLink route={{ page: "settings" }} current={route.page === "settings"} label={t("nav.settings")} icon="gear" onNavigate={closeMenu} />
              </li>
            </ul>
          </nav>
        </aside>

        <div className="main-column">
          <header className="topbar">
            <p className="demo-banner">
              <span className="demo-pill">
                <span className="demo-dot" aria-hidden="true" />
                {t("top.demo")}
              </span>
              <span className="demo-text">{t("top.demoText")}</span>
            </p>
            <div className="topbar-controls">
              <div className="topbar-slot" ref={setTopbarSlot} />
              <PreferenceControls preferences={preferences} onSaved={onPreferencesSaved} />
              <button
                type="button"
                className="top-button assistant-toggle"
                aria-expanded={assistantOpen}
                aria-controls="assistant"
                aria-label={assistantOpen ? t("assistant.close") : t("assistant.open")}
                title={assistantOpen ? t("assistant.close") : t("assistant.open")}
                onClick={() => setAssistantOpen((v) => !v)}
              >
                <Icon name="sparkle" size={20} />
              </button>
              <a
                className="avatar"
                href={hrefFor({ page: "settings" })}
                aria-label={t("top.profile", { name: profileName ?? t("settings.profile") })}
                onClick={(e) => {
                  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
                  e.preventDefault();
                  navigate({ page: "settings" });
                }}
              >
                <span className="avatar-initials" aria-hidden="true">
                  {profileName ? initials(profileName) : ""}
                </span>
                <Icon name="chevronDown" size={16} />
              </a>
            </div>
          </header>

          <main id="main" ref={mainRef} className="content" tabIndex={-1}>
            {children}
            <footer className="footer">
              <span>
                <Icon name="info" size={16} /> {t("footer.short")}
              </span>
              <span>{t("footer.disclaimer")}</span>
            </footer>
          </main>
        </div>

        <AssistantPanel open={assistantOpen} onClose={() => setAssistantOpen(false)} />
      </div>
    </ShellContext.Provider>
  );
}
