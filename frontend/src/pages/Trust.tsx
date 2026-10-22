import { useState } from "react";
import { EXPORT_URL, api } from "../api";
import { ErrorNotice, errorMessage, eventText, label, useLoad } from "../components/finance";
import { Card, PageHeader, DataTable, Field, FormError, Loading, Money, StatusBadge } from "../components/ui";
import { useI18n } from "../i18n";
import { navigate } from "../router";

/** Safety & Trust Center: approvals waiting for the person, readable activity log,
 * data mode, provenance and honest limits. Disclaimers never replace server checks. */
export function Trust() {
  const { t, formatDateTime } = useI18n();
  const proposals = useLoad(() => api.proposals(), []);
  const activity = useLoad(() => api.activity(), []);
  const pending = (proposals.data?.proposals ?? []).filter((p) => p.status === "ready_for_review" || p.status === "approved");

  return (
    <>
      <PageHeader icon="shield" title={t("nav.trust")} subtitle={t("page.trust.subtitle")} />
      <div className="grid-2">
        <Card title={t("trust.dataMode")} icon="info" tone="apricot">
          <p>
            <StatusBadge tone="accent">{t("app.demoBadge")}</StatusBadge>
          </p>
          <p>{t("trust.dataModeText")}</p>
          <p className="muted small">{t("trust.dataControls")}</p>
        </Card>
        <Card title={t("trust.pending")} icon="alertCircle" id="pending">
          <ErrorNotice error={proposals.error} />
          {!proposals.data ? (
            <Loading />
          ) : pending.length === 0 ? (
            <p className="muted">{t("trust.noPending")}</p>
          ) : (
            <ul className="event-list">
              {pending.map((p) => (
                <li key={p.id}>
                  <span>
                    <bdi>{p.terms.bill.description}</bdi> · <Money amount={p.terms.total_debit} currency={p.terms.source_currency} />{" "}
                    <StatusBadge tone={p.status === "approved" ? "warning" : "info"}>{label(t, "proposalStatus", p.status)}</StatusBadge>
                  </span>
                  <button type="button" className="btn btn-ghost btn-small" onClick={() => navigate({ page: "section", section: "payments" })}>
                    {t("trust.goToPayments")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <Card title={t("trust.activity")} icon="list" id="activity">
        <ErrorNotice error={activity.error} />
        {!activity.data ? (
          <Loading />
        ) : (
          <DataTable
            caption={t("trust.activity")}
            rows={activity.data.events}
            rowKey={(e) => String(e.id)}
            columns={[
              { key: "at", header: t("common.date"), render: (e) => formatDateTime(e.at) },
              { key: "what", header: t("common.description"), render: (e) => eventText(t, e) },
              {
                key: "amount",
                header: t("common.amount"),
                numeric: true,
                render: (e) => {
                  const amount = (e.details.total_debit ?? e.details.amount) as string | undefined;
                  const currency = e.details.currency as string | undefined;
                  return amount && currency ? <Money amount={amount} currency={currency} /> : null;
                },
              },
              {
                key: "sim",
                header: "",
                render: (e) => (e.details.simulated ? <StatusBadge tone="accent">{t("pay.simulated")}</StatusBadge> : null),
              },
            ]}
          />
        )}
      </Card>
      <div className="grid-2">
        <Card title={t("trust.provenance")} icon="info" id="provenance">
          <p>{t("trust.provenanceText")}</p>
          <p className="muted small">{t("currency.provider")}</p>
        </Card>
        <Card title={t("trust.limits")} icon="alert">
          <ul>
            <li>{t("trust.limit1")}</li>
            <li>{t("trust.limit2")}</li>
            <li>{t("trust.limit3")}</li>
          </ul>
        </Card>
      </div>
      <DataControls />
    </>
  );
}

/** Export, reset and delete act only on this session's workspace. Reset and delete need the
 * exact confirmation word typed here, and the server checks it again. */
function DataControls() {
  const { t } = useI18n();
  const [typed, setTyped] = useState<{ reset: string; delete: string }>({ reset: "", delete: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>, next: string) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      window.location.assign(next);
    } catch (err) {
      setError(errorMessage(err, t));
      setBusy(false);
    }
  };
  return (
    <Card title={t("data.title")} icon="shield" id="data-controls" tone="danger">
      <p>{t("data.scope")}</p>
      <div className="grid-3">
        <div>
          <h3 className="block-label">{t("data.export")}</h3>
          <p className="muted small">{t("data.exportHint")}</p>
          <a className="btn btn-secondary" href={EXPORT_URL} download>
            {t("data.exportButton")}
          </a>
        </div>
        <div>
          <h3 className="block-label">{t("data.reset")}</h3>
          <p className="muted small">{t("data.resetHint")}</p>
          <Field label={t("data.typeToConfirm", { word: "RESET" })}>
            {(props) => <input {...props} type="text" autoComplete="off" value={typed.reset} onChange={(e) => setTyped({ ...typed, reset: e.target.value })} />}
          </Field>
          <button type="button" className="btn btn-secondary" disabled={busy || typed.reset !== "RESET"} onClick={() => run(api.resetWorkspace, "/app/dashboard")}>
            {t("data.resetButton")}
          </button>
        </div>
        <div>
          <h3 className="block-label">{t("data.delete")}</h3>
          <p className="muted small">{t("data.deleteHint")}</p>
          <Field label={t("data.typeToConfirm", { word: "DELETE" })}>
            {(props) => <input {...props} type="text" autoComplete="off" value={typed.delete} onChange={(e) => setTyped({ ...typed, delete: e.target.value })} />}
          </Field>
          <button type="button" className="btn btn-danger" disabled={busy || typed.delete !== "DELETE"} onClick={() => run(api.deleteWorkspace, "/")}>
            {t("data.deleteButton")}
          </button>
        </div>
      </div>
      <FormError message={error} />
    </Card>
  );
}
