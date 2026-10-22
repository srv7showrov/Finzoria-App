import { useEffect, useState, type FormEvent } from "react";
import { ApiError, api, type FieldError, type Preferences } from "../api";
import { CurrencySelect, LanguageSelect, TimeZoneSelect } from "../components/inputs";
import { Card, PageHeader, Field, FormError, Loading } from "../components/ui";
import { useI18n } from "../i18n";
import { navigate } from "../router";

function errorText(err: unknown, t: ReturnType<typeof useI18n>["t"]): { message: string; fields: FieldError[] } {
  if (err instanceof ApiError) {
    if (err.status === 0) return { message: t("error.network"), fields: [] };
    if (err.status === 401) return { message: t("error.session"), fields: [] };
    if (err.code === "validation_error") return { message: t("error.validation"), fields: err.fields };
  }
  return { message: t("error.generic"), fields: [] };
}

type SaveState = { kind: "idle" } | { kind: "saving" } | { kind: "saved" } | { kind: "error"; message: string; fields: FieldError[] };

function SaveStatus({ state }: { state: SaveState }) {
  const { t } = useI18n();
  return (
    <>
      <p role="status" aria-live="polite" className="save-status">
        {state.kind === "saving" ? t("settings.saving") : state.kind === "saved" ? t("settings.saved") : ""}
      </p>
      {state.kind === "error" && <FormError message={state.message} fields={state.fields} />}
    </>
  );
}

export function Settings({ preferences, onPreferencesSaved }: { preferences: Preferences; onPreferencesSaved: (p: Preferences) => void }) {
  const { t } = useI18n();
  return (
    <>
      <PageHeader icon="gear" title={t("settings.title")} subtitle={t("page.settings.subtitle")} />
      <div className="grid-2">
        <ProfileForm />
        <PreferencesForm initial={preferences} onSaved={onPreferencesSaved} />
      </div>
      <div className="grid-2">
        <Card title={t("settings.dataControls")} icon="shield">
          <p className="muted">{t("settings.dataControlsPending")}</p>
          <button type="button" className="btn btn-secondary btn-small" onClick={() => navigate({ page: "section", section: "trust", hash: "data-controls" })}>
            {t("nav.trust")}
          </button>
        </Card>
        <Card title={t("nav.learn")} icon="book" tone="apricot">
          <p className="muted">{t("learn.subtitle")}</p>
          <button type="button" className="btn btn-secondary btn-small" onClick={() => navigate({ page: "learn" })}>
            {t("learn.title")}
          </button>
        </Card>
      </div>
    </>
  );
}

function ProfileForm() {
  const { t } = useI18n();
  const [name, setName] = useState<string | null>(null);
  const [institution, setInstitution] = useState("");
  const [state, setState] = useState<SaveState>({ kind: "idle" });

  useEffect(() => {
    api.profile().then(
      (p) => {
        setName(p.display_name);
        setInstitution(p.institution);
      },
      (err: unknown) => setState({ kind: "error", ...errorText(err, t) }),
    );
  }, [t]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (name === null) return;
    setState({ kind: "saving" });
    try {
      const saved = await api.saveProfile({ display_name: name, institution });
      setName(saved.display_name);
      setInstitution(saved.institution);
      setState({ kind: "saved" });
    } catch (err) {
      setState({ kind: "error", ...errorText(err, t) });
    }
  };

  return (
    <Card title={t("settings.profile")} icon="user" id="profile">
      {name === null && state.kind !== "error" ? (
        <Loading />
      ) : (
        <form onSubmit={submit}>
          <Field label={t("settings.displayName")} error={name !== null && name.trim() === "" ? t("form.required") : null}>
            {(props) => <input {...props} type="text" required maxLength={80} value={name ?? ""} onChange={(e) => setName(e.target.value)} />}
          </Field>
          <Field label={t("settings.institution")}>
            {(props) => <input {...props} type="text" maxLength={120} value={institution} onChange={(e) => setInstitution(e.target.value)} />}
          </Field>
          <button type="submit" className="btn btn-primary" disabled={state.kind === "saving" || !name?.trim()}>
            {t("settings.save")}
          </button>
          <SaveStatus state={state} />
        </form>
      )}
    </Card>
  );
}

function PreferencesForm({ initial, onSaved }: { initial: Preferences; onSaved: (p: Preferences) => void }) {
  const { t } = useI18n();
  const [language, setLanguage] = useState(initial.language);
  const [currency, setCurrency] = useState(initial.display_currency);
  const [timeZone, setTimeZone] = useState(initial.time_zone);
  const [state, setState] = useState<SaveState>({ kind: "idle" });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setState({ kind: "saving" });
    try {
      const saved = await api.savePreferences({ language, display_currency: currency, time_zone: timeZone });
      setState({ kind: "saved" });
      onSaved(saved);
    } catch (err) {
      setState({ kind: "error", ...errorText(err, t) });
    }
  };

  return (
    <Card title={t("settings.preferences")} icon="language" id="preferences">
      <form onSubmit={submit}>
        <LanguageSelect label={t("settings.language")} hint={t("settings.languageHint")} value={language} onChange={setLanguage} />
        <CurrencySelect label={t("settings.displayCurrency")} hint={t("settings.displayCurrencyHint")} value={currency} onChange={setCurrency} />
        <TimeZoneSelect label={t("settings.timeZone")} value={timeZone} onChange={setTimeZone} />
        <button type="submit" className="btn btn-primary" disabled={state.kind === "saving"}>
          {t("settings.save")}
        </button>
        <SaveStatus state={state} />
      </form>
    </Card>
  );
}
