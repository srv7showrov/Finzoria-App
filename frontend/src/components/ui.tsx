import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { FieldError } from "../api";
import { useI18n } from "../i18n";
import { Icon, type IconName } from "./icons";

/** Card with an optional heading, icon and actions. `id` lets Learn More and other links target it
 * (see useHashTarget in AppShell); `tone` selects a themed variant. */
export function Card({
  title,
  children,
  actions,
  icon,
  id,
  tone,
  className,
}: {
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
  icon?: IconName;
  id?: string;
  tone?: "apricot" | "danger";
  className?: string;
}) {
  const classes = ["card", tone ? `card-${tone}` : "", className ?? ""].filter(Boolean).join(" ");
  return (
    <section className={classes} id={id} tabIndex={id ? -1 : undefined}>
      {(title || actions) && (
        <header className="card-header">
          {title && (
            <h2>
              {icon && (
                <span className="card-icon" aria-hidden="true">
                  <Icon name={icon} size={20} />
                </span>
              )}
              {title}
            </h2>
          )}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

/** Page heading used by every section: lavender icon bubble, h1 (focused after navigation),
 * optional subtitle and right-aligned badges or actions. */
export function PageHeader({ icon, title, subtitle, children }: { icon: IconName; title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <div className="page-header">
      <span className="page-icon" aria-hidden="true">
        <Icon name={icon} size={26} />
      </span>
      <div className="page-title">
        <h1 tabIndex={-1}>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {children && <div className="page-header-extra">{children}</div>}
    </div>
  );
}

export interface TabItem {
  id: string;
  label: string;
  icon?: IconName;
  content: ReactNode;
}

/** Accessible tabs (WAI-ARIA tabs pattern, automatic activation). Panels stay mounted (hidden),
 * so form state survives switching. The selected tab is kept in the URL hash, and a hash that
 * names an element inside a panel (for example a Learn More link) selects that panel. */
export function Tabs({ label, items }: { label: string; items: TabItem[] }) {
  const baseId = useId();
  const panelFor = (hash: string): string | null => {
    if (!hash) return null;
    if (items.some((i) => i.id === hash)) return hash;
    const target = document.getElementById(hash);
    if (!target) return null;
    const panel = target.closest<HTMLElement>("[data-tab-panel]");
    return panel?.dataset.tabPanel ?? null;
  };
  const [selected, setSelected] = useState<string>(() => {
    const hash = decodeURIComponent(window.location.hash.slice(1));
    return items.some((i) => i.id === hash) ? hash : (items[0]?.id ?? "");
  });
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  // Elements inside panels only exist after the first render, so resolve the hash afterwards too.
  useEffect(() => {
    const sync = () => {
      const found = panelFor(decodeURIComponent(window.location.hash.slice(1)));
      if (found) setSelected(found);
    };
    sync();
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const select = (id: string, focus = false) => {
    setSelected(id);
    try {
      window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}#${id}`);
    } catch {
      /* ignore */
    }
    if (focus) refs.current[id]?.focus();
  };
  const onKey = (e: KeyboardEvent, index: number) => {
    const rtl = document.documentElement.dir === "rtl";
    const next = rtl ? "ArrowLeft" : "ArrowRight";
    const prev = rtl ? "ArrowRight" : "ArrowLeft";
    let to = -1;
    if (e.key === next) to = (index + 1) % items.length;
    else if (e.key === prev) to = (index - 1 + items.length) % items.length;
    else if (e.key === "Home") to = 0;
    else if (e.key === "End") to = items.length - 1;
    if (to < 0) return;
    e.preventDefault();
    select(items[to]!.id, true);
  };

  return (
    <div className="tabs">
      <div className="tab-list" role="tablist" aria-label={label}>
        {items.map((item, index) => (
          <button
            key={item.id}
            ref={(el) => {
              refs.current[item.id] = el;
            }}
            type="button"
            role="tab"
            id={`${baseId}-tab-${item.id}`}
            aria-selected={selected === item.id}
            aria-controls={`${baseId}-panel-${item.id}`}
            tabIndex={selected === item.id ? 0 : -1}
            className="tab"
            onClick={() => select(item.id)}
            onKeyDown={(e) => onKey(e, index)}
          >
            {item.icon && <Icon name={item.icon} size={18} />}
            {item.label}
          </button>
        ))}
      </div>
      {items.map((item) => (
        <div
          key={item.id}
          role="tabpanel"
          id={`${baseId}-panel-${item.id}`}
          aria-labelledby={`${baseId}-tab-${item.id}`}
          data-tab-panel={item.id}
          hidden={selected !== item.id}
          tabIndex={0}
          className="tab-panel"
        >
          {item.content}
        </div>
      ))}
    </div>
  );
}

/** Horizontally scrollable region for wide tables: keyboard-focusable, named, with a visible
 * hint and edge shadows when content is cut off. */
export function ScrollRegion({ label, children }: { label: string; children: ReactNode }) {
  const { t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ start: false, end: false });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const max = el.scrollWidth - el.clientWidth;
      const pos = Math.abs(el.scrollLeft); // negative in RTL
      setEdges({ start: pos > 1, end: max - pos > 1 });
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(update) : null;
    ro?.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      ro?.disconnect();
    };
  }, []);
  const scrollable = edges.start || edges.end;
  return (
    <div className={`scroll-shell${edges.start ? " cut-start" : ""}${edges.end ? " cut-end" : ""}`}>
      <div ref={ref} className="table-wrap" role="region" aria-label={t("table.region", { name: label })} tabIndex={0}>
        {children}
      </div>
      {scrollable && (
        <p className="scroll-hint" aria-hidden="true">
          {t("table.scrollHint")}
        </p>
      )}
    </div>
  );
}

export function Loading({ label }: { label?: string }) {
  const { t } = useI18n();
  return (
    <p className="loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label ?? t("loading")}
    </p>
  );
}

export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral" | "accent";

/** Status colours always come with a text label; colour is never the only signal. */
export function StatusBadge({ tone, children }: { tone: StatusTone; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Notice({ tone = "info", children }: { tone?: StatusTone; children: ReactNode }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === "danger" ? "alert" : undefined}>
      {children}
    </div>
  );
}

export function FormError({ message, fields = [] }: { message: string | null; fields?: FieldError[] }) {
  if (!message) return null;
  return (
    <div className="form-error" role="alert">
      <p>{message}</p>
      {fields.length > 0 && (
        <ul>
          {fields.map((f) => (
            <li key={f.field + f.message}>
              <strong>{f.field}</strong>: {f.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Visible label, optional hint and error, all linked to the control for screen readers. */
export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  children: (props: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {hint && (
        <p className="field-hint" id={hintId}>
          {hint}
        </p>
      )}
      {error && (
        <p className="field-error" id={errorId}>
          {error}
        </p>
      )}
    </div>
  );
}

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  numeric?: boolean;
}

export function DataTable<T>({ caption, columns, rows, rowKey }: { caption: string; columns: Column<T>[]; rows: T[]; rowKey: (row: T) => string }) {
  const { t } = useI18n();
  if (rows.length === 0) return <p className="muted">{t("table.empty")}</p>;
  return (
    <ScrollRegion label={caption}>
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={c.numeric ? "num" : undefined}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((c) => (
                <td key={c.key} className={c.numeric ? "num" : undefined}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  );
}

/** Shows an amount in its own currency; the ISO code is part of the formatted value. */
export function Money({ amount, currency }: { amount: string; currency: string }) {
  const { formatMoney } = useI18n();
  return (
    <span className="money" dir="ltr">
      {formatMoney(amount, currency)}
    </span>
  );
}
