import { useState } from "react";
import { api, type InvoiceExtraction } from "../api";
import { Chat, notifyDataChanged } from "../components/Chat";
import { errorMessage, label } from "../components/finance";
import assistantPortrait from "../assets/assistant-portrait.webp";
import { Card, Notice, PageHeader, StatusBadge } from "../components/ui";
import { useI18n } from "../i18n";
import { navigate } from "../router";
import { BillForm } from "./Payments";

export function Workspace() {
  const { t } = useI18n();
  return (
    <>
      <PageHeader icon="sparkle" title={t("nav.workspace")} subtitle={t("page.workspace.subtitle")}>
        <StatusBadge tone="accent">{t("app.demoBadge")}</StatusBadge>
      </PageHeader>
      <div className="workspace-layout">
        <Card title={t("ai.chatTitle")} icon="sparkle" id="chat" className="chat-card">
          <Chat />
        </Card>
        <div className="workspace-side">
          <section className="card card-apricot assistant-how" aria-labelledby="ai-how-title">
            <img className="assistant-how-portrait" src={assistantPortrait} alt="" width={520} height={435} decoding="async" />
            <h2 id="ai-how-title">{t("ai.howTitle")}</h2>
            <ul>
              <li>{t("ai.how1")}</li>
              <li>{t("ai.how2")}</li>
              <li>{t("ai.how3")}</li>
            </ul>
          </section>
          <InvoicePanel />
        </div>
      </div>
    </>
  );
}

/** Pasted invoice text -> AI suggestion -> the user reviews every field -> saves the bill.
 * Manual entry is always available. Nothing is saved without the user's Save click. */
function InvoicePanel() {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extraction, setExtraction] = useState<InvoiceExtraction | null>(null);
  const [manual, setManual] = useState(false);
  const [saved, setSaved] = useState(false);

  const extract = async () => {
    setBusy(true);
    setError(null);
    setExtraction(null);
    setSaved(false);
    try {
      setExtraction(await api.extractInvoice(text));
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  const f = extraction?.fields;
  return (
    <Card title={t("ai.invoiceTitle")} icon="receipt" id="invoice">
      <p className="muted small">{t("ai.invoiceUntrusted")}</p>
      <label htmlFor="invoice-text" className="block-label">
        {t("ai.invoicePaste")}
      </label>
      <textarea id="invoice-text" rows={6} maxLength={8000} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="actions">
        <button type="button" className="btn btn-primary" disabled={busy || !text.trim()} onClick={extract}>
          {busy ? t("ai.thinking") : t("ai.invoiceExtract")}
        </button>
        <button type="button" className="btn btn-ghost" onClick={() => (setManual(true), setExtraction(null), setSaved(false))}>
          {t("ai.invoiceManual")}
        </button>
      </div>
      {error && <Notice tone="danger">{error}</Notice>}
      {saved && (
        <Notice tone="success">
          {t("ai.invoiceSaved")}{" "}
          <button type="button" className="btn btn-ghost btn-small" onClick={() => navigate({ page: "section", section: "payments" })}>
            {t("ai.reviewInPayments")}
          </button>
        </Notice>
      )}
      {extraction && (
        <>
          <Notice tone="warning">{t("ai.invoiceReview")}</Notice>
          {extraction.warnings.length > 0 && (
            <ul className="muted small">
              {extraction.warnings.map((w) => (
                <li key={w}>{label(t, "ai.invoiceWarning", w)}</li>
              ))}
            </ul>
          )}
          {extraction.notes.length > 0 && (
            <details>
              <summary>{t("ai.invoiceNotes")}</summary>
              <ul className="small">
                {extraction.notes.map((n) => (
                  <li key={n}>
                    <bdi>{n}</bdi>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
      {(extraction || manual) && !saved && (
        <BillForm
          key={JSON.stringify(f ?? "manual")}
          title={extraction ? t("ai.invoiceReviewTitle") : t("pay.addBill")}
          submitLabel={t("ai.invoiceSave")}
          initial={
            f
              ? {
                  id: "",
                  description: f.description ?? "",
                  payee: f.payee ?? "",
                  category: "tuition",
                  amount: f.amount ?? "",
                  currency: f.currency ?? "AUD",
                  due_date: f.due_date ?? "",
                  status: "open",
                  version: 0,
                  settled_on: null,
                  settled_by_execution_id: null,
                }
              : undefined
          }
          onSubmit={async (bill) => {
            await api.createBill(bill);
            setSaved(true);
            setExtraction(null);
            setManual(false);
            setText("");
            notifyDataChanged();
          }}
        />
      )}
    </Card>
  );
}
