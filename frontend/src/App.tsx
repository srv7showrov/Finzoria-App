import { useCallback, useEffect, useState } from "react";
import { ApiError, SESSION_INVALID_EVENT, api, type Preferences } from "./api";
import { AppShell } from "./components/AppShell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Logo } from "./components/Logo";
import { Loading, Notice } from "./components/ui";
import { I18nProvider, isLocale, useI18n, type Locale } from "./i18n";
import { Budget } from "./pages/Budget";
import { Currency } from "./pages/Currency";
import { Dashboard } from "./pages/Dashboard";
import { Landing } from "./pages/Landing";
import { LearnMore } from "./pages/LearnMore";
import { Payments } from "./pages/Payments";
import { SectionPlaceholder } from "./pages/SectionPlaceholder";
import { Settings } from "./pages/Settings";
import { Trust } from "./pages/Trust";
import { Workspace } from "./pages/Workspace";
import { Funding } from "./pages/Funding";
import { Reports } from "./pages/Reports";
import { navigate, useRoute, type Section } from "./router";

type SessionState =
  | { status: "loading" }
  | { status: "ready"; preferences: Preferences }
  | { status: "error"; error: ApiError }
  | { status: "invalid" };

export function App() {
  const route = useRoute();
  const [locale, setLocale] = useState<Locale>("en");
  const [session, setSession] = useState<SessionState>({ status: "loading" });
  const inApp = route.page !== "landing";

  const applyPreferences = useCallback((preferences: Preferences) => {
    if (isLocale(preferences.language)) setLocale(preferences.language);
    setSession({ status: "ready", preferences });
  }, []);

  // A 401 while using the app means this browser's session is no longer valid on this server.
  // Show a recovery screen; never switch to another workspace or resend anything automatically.
  useEffect(() => {
    const onInvalid = () => setSession((s) => (s.status === "ready" ? { status: "invalid" } : s));
    window.addEventListener(SESSION_INVALID_EVENT, onInvalid);
    return () => window.removeEventListener(SESSION_INVALID_EVENT, onInvalid);
  }, []);

  useEffect(() => {
    if (!inApp || session.status === "ready" || session.status === "invalid") return;
    let cancelled = false;
    (async () => {
      try {
        // Opening an app link without a session starts a fictional demo workspace.
        await api.session().catch(async (err: unknown) => {
          if (err instanceof ApiError && err.status === 401) return api.startSession();
          throw err;
        });
        const preferences = await api.preferences();
        if (!cancelled) applyPreferences(preferences);
      } catch (err) {
        if (!cancelled) setSession({ status: "error", error: err instanceof ApiError ? err : new ApiError(0, "unknown", String(err)) });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [inApp, session.status, applyPreferences]);

  const start = async (target: "settings" | Section) => {
    const result = await api.startSession();
    if (result.created && locale !== "en") {
      const current = await api.preferences();
      applyPreferences(await api.savePreferences({ language: locale, display_currency: current.display_currency, time_zone: current.time_zone }));
    }
    navigate(target === "settings" ? { page: "settings" } : { page: "section", section: target });
  };

  return (
    <I18nProvider locale={locale} timeZone={session.status === "ready" ? session.preferences.time_zone : undefined}>
      {route.page === "landing" ? (
        <Landing locale={locale} onLocaleChange={setLocale} onStart={start} />
      ) : session.status === "loading" ? (
        <StatusScreen>
          <Loading />
        </StatusScreen>
      ) : session.status === "error" ? (
        <SessionError error={session.error} onRetry={() => setSession({ status: "loading" })} />
      ) : session.status === "invalid" ? (
        <SessionInvalid
          onStartNew={async () => {
            await api.startSession(); // the server issues a NEW workspace for an unknown cookie
            setSession({ status: "loading" });
            navigate({ page: "section", section: "dashboard" });
          }}
        />
      ) : (
        <AppShell route={route} preferences={session.preferences} onPreferencesSaved={applyPreferences}>
          {/* Remount the page when the display currency changes so every view re-reads converted figures. */}
          <ErrorBoundary resetKey={JSON.stringify(route)} key={session.preferences.display_currency}>
          {route.page === "settings" ? (
            <Settings preferences={session.preferences} onPreferencesSaved={applyPreferences} />
          ) : route.page === "learn" ? (
            <LearnMore />
          ) : route.section === "dashboard" ? (
            <Dashboard />
          ) : route.section === "budget" ? (
            <Budget />
          ) : route.section === "currency" ? (
            <Currency />
          ) : route.section === "payments" ? (
            <Payments />
          ) : route.section === "trust" ? (
            <Trust />
          ) : route.section === "workspace" ? (
            <Workspace />
          ) : route.section === "funding" ? (
            <Funding />
          ) : route.section === "reports" ? (
            <Reports />
          ) : (
            <SectionPlaceholder section={route.section} />
          )}
          </ErrorBoundary>
        </AppShell>
      )}
    </I18nProvider>
  );
}

function SessionInvalid({ onStartNew }: { onStartNew: () => Promise<void> }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  return (
    <StatusScreen labelledBy="session-invalid-title">
      <h1 id="session-invalid-title" tabIndex={-1}>
        {t("session.invalidTitle")}
      </h1>
      <p>{t("session.invalidText")}</p>
      <p className="muted small">{t("session.invalidNoReplay")}</p>
      {failed && <Notice tone="danger">{t("error.network")}</Notice>}
      <div className="actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setFailed(false);
            try {
              await onStartNew();
            } catch {
              setFailed(true);
            } finally {
              setBusy(false);
            }
          }}
        >
          {t("session.startNew")}
        </button>
        <a className="btn btn-ghost" href="/">
          {t("session.backToStart")}
        </a>
      </div>
    </StatusScreen>
  );
}

function SessionError({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <StatusScreen labelledBy="session-error-title">
      <h1 id="session-error-title" tabIndex={-1}>
        {t("session.errorTitle")}
      </h1>
      <Notice tone="danger">{error.status === 0 ? t("error.network") : t("error.generic")}</Notice>
      <div className="actions">
        <button type="button" className="btn btn-primary" onClick={onRetry}>
          {t("app.retry")}
        </button>
        <a className="btn btn-ghost" href="/">
          {t("session.backToStart")}
        </a>
      </div>
    </StatusScreen>
  );
}

/** Full-page state outside the app shell (starting, session ended, server unreachable). */
function StatusScreen({ labelledBy, children }: { labelledBy?: string; children: React.ReactNode }) {
  const { t } = useI18n();
  return (
    <main className="status-screen" aria-labelledby={labelledBy}>
      <Logo name={t("app.name")} tagline={t("app.tagline")} />
      <div className="card status-card">{children}</div>
    </main>
  );
}
