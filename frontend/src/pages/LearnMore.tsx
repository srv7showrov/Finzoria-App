import { useState } from "react";
import assistantPortrait from "../assets/assistant-portrait.webp";
import { Icon, type IconName } from "../components/icons";
import { PageHeader } from "../components/ui";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n/types";
import { hrefFor, navigate, type Route, type Section } from "../router";

type Group = Section | "settings";

interface Feature {
  id: string;
  group: Group;
  icon: IconName;
  route: Route;
  example?: boolean;
}

/** Feature-level explanations, grouped by the eight sections plus Settings. Each card opens the
 * working view (hash targets select the right tab or card). Text lives in the i18n catalogs under
 * learn.c.<id>.(title|what|how|why|ex) and describes behaviour verified in the implementation. */
const FEATURES: Feature[] = [
  { id: "overview", group: "dashboard", icon: "home", route: { page: "section", section: "dashboard" } },
  { id: "deadlines", group: "dashboard", icon: "calendar", route: { page: "section", section: "dashboard", hash: "deadlines" } },
  { id: "chat", group: "workspace", icon: "sparkle", route: { page: "section", section: "workspace", hash: "chat" }, example: true },
  { id: "confirm", group: "workspace", icon: "checkCircle", route: { page: "section", section: "workspace", hash: "chat" } },
  { id: "invoice", group: "workspace", icon: "receipt", route: { page: "section", section: "workspace", hash: "invoice" } },
  { id: "bills", group: "payments", icon: "receipt", route: { page: "section", section: "payments", hash: "bills" } },
  { id: "routes", group: "payments", icon: "globe", route: { page: "section", section: "payments", hash: "compare" } },
  { id: "approve", group: "payments", icon: "shield", route: { page: "section", section: "payments", hash: "proposals" } },
  { id: "run", group: "payments", icon: "checkCircle", route: { page: "section", section: "payments", hash: "history" }, example: true },
  { id: "rates", group: "currency", icon: "coins", route: { page: "section", section: "currency", hash: "rates" } },
  { id: "converter", group: "currency", icon: "globe", route: { page: "section", section: "currency", hash: "converter" }, example: true },
  { id: "targets", group: "currency", icon: "target", route: { page: "section", section: "currency", hash: "targets" } },
  { id: "rateScenario", group: "currency", icon: "chart", route: { page: "section", section: "currency", hash: "rate-scenario" } },
  { id: "planActual", group: "budget", icon: "chart", route: { page: "section", section: "budget", hash: "overview" }, example: true },
  { id: "recordPaid", group: "budget", icon: "checkCircle", route: { page: "section", section: "budget", hash: "planned-items" } },
  { id: "contributions", group: "budget", icon: "plusCircle", route: { page: "section", section: "budget", hash: "contributions" }, example: true },
  { id: "reserve", group: "budget", icon: "shield", route: { page: "section", section: "budget", hash: "reserve" } },
  { id: "goals", group: "budget", icon: "target", route: { page: "section", section: "budget", hash: "goals" } },
  { id: "forecast", group: "budget", icon: "chart", route: { page: "section", section: "budget", hash: "forecast" } },
  { id: "scenarios", group: "budget", icon: "bolt", route: { page: "section", section: "budget", hash: "scenario" } },
  { id: "applications", group: "funding", icon: "doc", route: { page: "section", section: "funding", hash: "applications" } },
  { id: "checklists", group: "funding", icon: "list", route: { page: "section", section: "funding", hash: "checklists" } },
  { id: "workIncome", group: "funding", icon: "coins", route: { page: "section", section: "funding", hash: "work-income" }, example: true },
  { id: "resources", group: "funding", icon: "book", route: { page: "section", section: "funding", hash: "resources" } },
  { id: "pending", group: "trust", icon: "alertCircle", route: { page: "section", section: "trust", hash: "pending" } },
  { id: "activity", group: "trust", icon: "list", route: { page: "section", section: "trust", hash: "activity" } },
  { id: "provenance", group: "trust", icon: "info", route: { page: "section", section: "trust", hash: "provenance" } },
  { id: "dataControls", group: "trust", icon: "shield", route: { page: "section", section: "trust", hash: "data-controls" } },
  { id: "report", group: "reports", icon: "doc", route: { page: "section", section: "reports", hash: "report-summary" } },
  { id: "export", group: "reports", icon: "receipt", route: { page: "section", section: "reports", hash: "export" } },
  { id: "preferences", group: "settings", icon: "gear", route: { page: "settings", hash: "preferences" } },
];

const GROUPS: Group[] = ["dashboard", "workspace", "payments", "currency", "budget", "funding", "trust", "reports", "settings"];
const GROUP_ICONS: Record<Group, IconName> = {
  dashboard: "home",
  workspace: "sparkle",
  payments: "card",
  currency: "globe",
  budget: "chart",
  funding: "cap",
  trust: "shield",
  reports: "doc",
  settings: "gear",
};

const groupName = (t: (k: MessageKey) => string, g: Group) => (g === "settings" ? t("nav.settings") : t(`nav.short.${g}` as MessageKey));

export function LearnMore() {
  const { t } = useI18n();
  const [filter, setFilter] = useState<Group | "all">("all");
  const groups = filter === "all" ? GROUPS : [filter];
  const count = FEATURES.filter((f) => groups.includes(f.group)).length;

  return (
    <>
      <PageHeader icon="book" title={t("learn.title")} subtitle={t("learn.subtitle")} />
      <section className="card card-apricot learn-distinctions" aria-labelledby="learn-distinctions">
        <div className="learn-distinctions-head">
          <h2 id="learn-distinctions">{t("learn.distinctions")}</h2>
          <img className="learn-portrait" src={assistantPortrait} alt="" width={520} height={435} decoding="async" />
        </div>
        <ul>
          {(["learn.d1", "learn.d2", "learn.d3", "learn.d4", "learn.d5", "learn.d6"] as const).map((k) => (
            <li key={k}>
              <Icon name="checkCircle" size={18} />
              <span>{t(k)}</span>
            </li>
          ))}
        </ul>
      </section>
      <div className="filter-bar" id="learn-filters" tabIndex={-1} role="group" aria-label={t("learn.filter")}>
        {(["all", ...GROUPS] as const).map((g) => (
          <button key={g} type="button" className="filter-chip" aria-pressed={filter === g} onClick={() => setFilter(g)}>
            {g !== "all" && <Icon name={GROUP_ICONS[g]} size={16} />}
            {g === "all" ? t("learn.all") : groupName(t, g)}
          </button>
        ))}
      </div>
      <p className="muted small" role="status" aria-live="polite">
        {t("learn.count", { count })}
      </p>
      {groups.map((g) => (
        <section key={g} className="learn-group" aria-labelledby={`learn-${g}`}>
          <h2 id={`learn-${g}`} className="learn-group-title">
            <span className="card-icon" aria-hidden="true">
              <Icon name={GROUP_ICONS[g]} size={20} />
            </span>
            {groupName(t, g)}
          </h2>
          <div className="learn-grid">
            {FEATURES.filter((f) => f.group === g).map((f) => (
              <FeatureCard key={f.id} feature={f} />
            ))}
          </div>
          <a className="back-to-filters" href="#learn-filters">
            <Icon name="arrow" size={16} className="up" />
            {t("learn.backToFilters")}
          </a>
        </section>
      ))}
    </>
  );
}

function FeatureCard({ feature }: { feature: Feature }) {
  const { t } = useI18n();
  const k = (part: string) => t(`learn.c.${feature.id}.${part}` as MessageKey);
  const title = k("title");
  return (
    <article className="learn-card" aria-labelledby={`lc-${feature.id}`}>
      <h3 id={`lc-${feature.id}`}>
        <span className="learn-icon" aria-hidden="true">
          <Icon name={feature.icon} size={22} />
        </span>
        {title}
      </h3>
      <dl>
        <div>
          <dt>{t("learn.what")}</dt>
          <dd>{k("what")}</dd>
        </div>
        <div>
          <dt>{t("learn.how")}</dt>
          <dd>{k("how")}</dd>
        </div>
        <div>
          <dt>{t("learn.why")}</dt>
          <dd>{k("why")}</dd>
        </div>
      </dl>
      {feature.example && (
        <details className="inline-details learn-example">
          <summary>{t("learn.example")}</summary>
          <p>{k("ex")}</p>
        </details>
      )}
      <a
        className="link-arrow learn-open"
        href={hrefFor(feature.route)}
        onClick={(e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
          e.preventDefault();
          navigate(feature.route);
        }}
      >
        {t("learn.open")}
        <span className="sr-only"> – {title}</span> <Icon name="arrow" size={18} />
      </a>
    </article>
  );
}
