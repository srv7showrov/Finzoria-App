import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type AiStatus, type AssistantAction, type ChatMessage, type ChatMode, type ConversationDetail, type ToolCallView, type ToolCard } from "../api";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n/types";
import { navigate } from "../router";
import { errorMessage, label } from "./finance";
import { Loading, Money, Notice, StatusBadge } from "./ui";

const CONVERSATION_KEY = "finzoria-conversation";
export const OPEN_PROPOSAL_KEY = "finzoria-open-proposal";

function storedConversation(): string | null {
  try {
    return window.localStorage.getItem(CONVERSATION_KEY);
  } catch {
    return null;
  }
}

function storeConversation(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(CONVERSATION_KEY, id);
    else window.localStorage.removeItem(CONVERSATION_KEY);
  } catch {
    /* per-viewer convenience only */
  }
}

/** Tell open pages that financial data changed (after a confirmed action). */
export function notifyDataChanged(): void {
  window.dispatchEvent(new Event("finzoria:data-changed"));
}

type Row = Record<string, unknown>;
const str = (v: unknown): string => (v === null || v === undefined ? "" : String(v));

function Amount({ value, currency }: { value: unknown; currency: unknown }) {
  if (value === null || value === undefined || !currency) return <>—</>;
  return <Money amount={str(value)} currency={str(currency)} />;
}

function ActionCard({ action, onChanged }: { action: AssistantAction | undefined; onChanged: () => void }) {
  const { t, formatDate } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!action) return null;
  const p = action.payload;
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      notifyDataChanged();
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(false);
      onChanged();
    }
  };
  const currency = p.currency ?? "";
  return (
    <div className="tool-card action-card">
      <p className="tool-card-title">
        {t(`ai.action.${action.kind}` as MessageKey)}{" "}
        <StatusBadge tone={action.status === "pending" ? "warning" : action.status === "confirmed" ? "success" : "neutral"}>
          {t(`ai.actionStatus.${action.status}` as MessageKey)}
        </StatusBadge>
      </p>
      <dl className="terms compact">
        {p.description || p.contributor || p.payee ? (
          <div>
            <dt>{t("common.description")}</dt>
            <dd>
              <bdi>{p.description || p.contributor || p.payee}</bdi>
            </dd>
          </div>
        ) : null}
        <div>
          <dt>{t("common.amount")}</dt>
          <dd>
            <Amount value={p.amount} currency={currency} />
          </dd>
        </div>
        {(p.due_date || p.expected_date || p.start_date) && (
          <div>
            <dt>{t("common.date")}</dt>
            <dd>{formatDate(str(p.due_date || p.expected_date || p.start_date))}</dd>
          </div>
        )}
        {p.category && (
          <div>
            <dt>{t("common.category")}</dt>
            <dd>{label(t, "cat", str(p.category))}</dd>
          </div>
        )}
      </dl>
      {action.kind === "contribution" && <p className="muted small">{t("ai.contributionExpectedOnly")}</p>}
      {action.status === "pending" && (
        <div className="actions">
          <button type="button" className="btn btn-primary btn-small" disabled={busy} onClick={() => act(() => api.confirmAction(action.id))}>
            {t("ai.confirm")}
          </button>
          <button type="button" className="btn btn-ghost btn-small" disabled={busy} onClick={() => act(() => api.dismissAction(action.id))}>
            {t("ai.dismiss")}
          </button>
        </div>
      )}
      {error && <p className="field-error">{error}</p>}
    </div>
  );
}

function ToolCardView({ call, actions, onChanged }: { call: ToolCallView; actions: AssistantAction[]; onChanged: () => void }) {
  const { t, formatDate } = useI18n();
  const toolName = label(t, "ai.tool", call.tool);
  if (call.status !== "ok" || !call.card) {
    return (
      <p className="tool-step muted small">
        {t("ai.toolFailed", { tool: toolName })} {call.error ? `(${call.error})` : ""}
      </p>
    );
  }
  const c = call.card as ToolCard & Row;
  const d = str(c.display_currency);
  let body = null;
  switch (c.type) {
    case "summary": {
      const budget = c.budget as Row;
      const forecast = c.forecast_not_available_cash as Row;
      const reserve = c.reserve as Row | null;
      body = (
        <dl className="terms compact">
          {(c.actual_balances as Row[]).map((a) => (
            <div key={str(a.id)}>
              <dt>
                <bdi>{str(a.name)}</bdi>
              </dt>
              <dd>
                <Amount value={a.balance} currency={a.currency} />
              </dd>
            </div>
          ))}
          <div>
            <dt>{t("dashboard.plannedRemainder")}</dt>
            <dd>
              <Amount value={budget.planned_remainder} currency={d} />
            </dd>
          </div>
          <div>
            <dt>{t("dashboard.endConfirmed", { date: formatDate(str(forecast.to)) })}</dt>
            <dd>
              <Amount value={forecast.projected_end_confirmed} currency={d} /> <span className="muted small">({t("label.forecast")})</span>
            </dd>
          </div>
          {reserve && (
            <div>
              <dt>{t("dashboard.headroom")}</dt>
              <dd>
                <Amount value={reserve.headroom} currency={reserve.currency} />
              </dd>
            </div>
          )}
        </dl>
      );
      break;
    }
    case "budget":
    case "report": {
      const totals = (c.type === "report" ? c.totals : c) as Row;
      body = (
        <dl className="terms compact">
          {(["planned_income", "planned_expenses", "planned_remainder", "actual_income", "actual_expenses"] as const).map((k) => (
            <div key={k}>
              <dt>{t(`ai.figure.${k}` as MessageKey)}</dt>
              <dd>
                <Amount value={totals[k]} currency={d} />
              </dd>
            </div>
          ))}
        </dl>
      );
      break;
    }
    case "conversion": {
      const rate = c.rate as Row;
      body = (
        <p>
          <Amount value={c.amount} currency={c.from} /> = <Amount value={c.result} currency={c.to} />{" "}
          <span className="muted small" dir="ltr">
            {t("valuation.rate", { base: str(rate.base), quote: str(rate.quote), rate: str(rate.rate), mode: label(t, "rate.mode", str(rate.mode)) })}
          </span>
        </p>
      );
      break;
    }
    case "quotes": {
      const cur = str((c.objective as Row).source_currency);
      body = (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t("table.route")}</th>
                <th scope="col" className="num">
                  {t("pay.total")}
                </th>
                <th scope="col">{t("pay.arrival")}</th>
                <th scope="col">{t("common.status")}</th>
              </tr>
            </thead>
            <tbody>
              {(c.routes as Row[]).map((r) => (
                <tr key={str(r.route)}>
                  <td>{t("route.name", { code: str(r.route) })}</td>
                  <td className="num">
                    <Amount value={r.total_debit} currency={cur} />
                  </td>
                  <td>{formatDate(str(r.estimated_arrival))}</td>
                  <td>
                    <StatusBadge tone={r.on_time ? "success" : "danger"}>{r.on_time ? t("pay.onTime") : t("pay.late")}</StatusBadge>{" "}
                    <StatusBadge tone={r.reserve_ok ? "success" : "danger"}>{r.reserve_ok ? t("pay.reserveOk") : t("pay.reserveBreach")}</StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      break;
    }
    case "scenario": {
      const base = c.baseline as Row;
      const scen = c.scenario as Row;
      body = (
        <>
          <dl className="terms compact">
            <div>
              <dt>{t("scenario.baseline")}</dt>
              <dd>
                <Amount value={base.projected_end_with_expected} currency={base.display_currency} />
              </dd>
            </div>
            <div>
              <dt>{t("scenario.result")}</dt>
              <dd>
                <Amount value={scen.projected_end_with_expected} currency={scen.display_currency} />
              </dd>
            </div>
          </dl>
          {Array.isArray(c.payment_timing) &&
            (c.payment_timing as Row[])
              .filter((x) => x.case === "scenario")
              .map((x) => (
                <ul key={str(x.bill_id)} className="muted small">
                  {(x.routes as Row[]).map((r) => (
                    <li key={str(r.route)}>
                      {t("route.name", { code: str(r.route) })}:{" "}
                      {r.status === "indeterminate"
                        ? t("scenario.indeterminate")
                        : r.feasible
                          ? `${formatDate(str(r.estimated_arrival))} · ${r.on_time ? t("pay.onTime") : t("pay.late")}`
                          : t("scenario.notFeasible")}
                    </li>
                  ))}
                </ul>
              ))}
          <p className="muted small">{t("scenario.note")}</p>
        </>
      );
      break;
    }
    case "payment_proposal": {
      const terms = c.terms as Row;
      const checks = (c.checks as Row | null) ?? {};
      const blocking = (checks.blocking as string[] | undefined) ?? [];
      body = (
        <>
          <p className="simulated-banner small">{t("pay.simulated")}</p>
          <dl className="terms compact">
            <div>
              <dt>{t("pay.recipientAmount")}</dt>
              <dd>
                <Amount value={terms.recipient_amount} currency={terms.recipient_currency} />
              </dd>
            </div>
            <div>
              <dt>{t("pay.total")}</dt>
              <dd>
                <Amount value={terms.total_debit} currency={terms.source_currency} />
              </dd>
            </div>
            <div>
              <dt>{t("pay.arrival")}</dt>
              <dd>{formatDate(str(terms.estimated_arrival))}</dd>
            </div>
            <div>
              <dt>{t("common.status")}</dt>
              <dd>{label(t, "proposalStatus", str(c.status))}</dd>
            </div>
          </dl>
          {blocking.length > 0 && (
            <ul className="muted small">
              {blocking.map((b) => (
                <li key={b}>{label(t, "pay.block", b)}</li>
              ))}
            </ul>
          )}
          <p className="muted small">{t("ai.approvalInPayments")}</p>
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={() => {
              try {
                window.sessionStorage.setItem(OPEN_PROPOSAL_KEY, str(c.proposal_id));
              } catch {
                /* ignore */
              }
              navigate({ page: "section", section: "payments" });
            }}
          >
            {t("ai.reviewInPayments")}
          </button>
        </>
      );
      break;
    }
    case "pending_action":
      return <ActionCard action={actions.find((a) => a.id === c.action_id)} onChanged={onChanged} />;
    case "status":
      body = <p>{label(t, "proposalStatus", str(c.status))}</p>;
      break;
    default:
      body = null;
  }
  return (
    <div className="tool-card">
      <p className="tool-card-title">{toolName}</p>
      {body}
    </div>
  );
}

function MessageView({ m, actions, onChanged }: { m: ChatMessage; actions: AssistantAction[]; onChanged: () => void }) {
  const { t } = useI18n();
  if (m.role === "user") {
    return (
      <div className="chat-msg chat-user">
        <p className="chat-text">
          <bdi>{m.content}</bdi>
        </p>
      </div>
    );
  }
  return (
    <div className="chat-msg chat-assistant">
      {m.tool_calls.map((call, i) => (
        <ToolCardView key={i} call={call} actions={actions} onChanged={onChanged} />
      ))}
      {m.content && <p className="chat-text">{m.content}</p>}
      {m.status !== "ok" && (
        <Notice tone={m.status === "failed" ? "danger" : "warning"}>
          {t(`ai.status.${m.status}` as MessageKey)} {m.error_code ? label(t, "ai.error", m.error_code) : ""}
        </Notice>
      )}
      {!!m.model_requests && <p className="muted small">{t("ai.modelRequests", { count: m.model_requests })}</p>}
    </div>
  );
}

/** AI Financial Workspace chat. Shows the real connection state; when the assistant is not
 * configured the input is disabled and no reply is simulated. */
export function Chat({ compact = false }: { compact?: boolean }) {
  const { t } = useI18n();
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(storedConversation);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<ChatMode>("concise");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.aiStatus().then(setStatus, () => setStatus(null));
  }, []);

  const load = (id: string | null) => {
    if (!id) {
      setDetail(null);
      return;
    }
    api.conversation(id).then(setDetail, () => {
      storeConversation(null);
      setConversationId(null);
      setDetail(null);
    });
  };
  // Effects must return nothing or a cleanup function. Block bodies matter: in browsers where
  // scrollIntoView() returns a Promise, an arrow expression body handed that Promise to React as a
  // "cleanup", which crashed the whole page on unmount ("l is not a function").
  useEffect(() => {
    load(conversationId);
  }, [conversationId]);
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [detail]);

  const available = status !== null && status.state !== "unavailable";
  const send = async (e: FormEvent) => {
    e.preventDefault();
    if (!message.trim() || sending) return;
    setSending(true);
    setError(null);
    try {
      const result = await api.chat({ message, mode, ...(conversationId ? { conversation_id: conversationId } : {}) });
      setMessage("");
      storeConversation(result.conversation_id);
      setConversationId(result.conversation_id);
      setDetail(result.conversation);
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setSending(false);
      api.aiStatus().then(setStatus, () => undefined);  // refresh the request counts
    }
  };

  return (
    <div className={`chat${compact ? " chat-compact" : ""}`}>
      {status === null ? (
        <Loading />
      ) : !available ? (
        <Notice tone="neutral">
          <p>{t("ai.unavailableShort")}</p>
          {/* Configuration details are for whoever runs the server, so they stay folded away. */}
          <details className="inline-details setup-help">
            <summary>{t("ai.setupHelp")}</summary>
            <p className="small">{t("ai.unavailableHelp")}</p>
          </details>
        </Notice>
      ) : (
        <p>
          <StatusBadge tone={status.state === "connected" ? "success" : status.state === "failed" ? "danger" : "warning"}>
            {t(`assistant.state.${status.state}` as MessageKey)}
          </StatusBadge>
          {status.provider && status.model && (
            <span className="muted small">
              {" "}
              {t("ai.provider", { provider: status.provider, model: status.model })}
            </span>
          )}
          {status.requests && (
            <span className="muted small" style={{ display: "block" }}>
              {t("ai.requestCount", { day: status.requests.last_24h, failed: status.requests.failed_last_24h })}
            </span>
          )}
        </p>
      )}
      <div className="chat-log" aria-live="polite">
        {detail?.messages.map((m) => <MessageView key={m.id} m={m} actions={detail.actions} onChanged={() => load(conversationId)} />)}
        {sending && <Loading label={t("ai.thinking")} />}
        <div ref={endRef} />
      </div>
      {error && <Notice tone="danger">{error}</Notice>}
      <form className="chat-form" onSubmit={send}>
        <label htmlFor={compact ? "chat-input-compact" : "chat-input"}>{t("ai.inputLabel")}</label>
        <textarea
          id={compact ? "chat-input-compact" : "chat-input"}
          value={message}
          maxLength={4000}
          rows={compact ? 2 : 3}
          disabled={!available || sending}
          placeholder={t("ai.placeholder")}
          onChange={(e) => setMessage(e.target.value)}
        />
        <div className="chat-controls">
          <fieldset className="inline-radio">
            <legend className="sr-only">{t("ai.mode")}</legend>
            {(["concise", "detailed"] as const).map((m) => (
              <label key={m} className="inline">
                <input type="radio" name={compact ? "mode-compact" : "mode"} checked={mode === m} onChange={() => setMode(m)} /> {t(`ai.mode.${m}`)}
              </label>
            ))}
          </fieldset>
          <button type="submit" className="btn btn-primary" disabled={!available || sending || !message.trim()}>
            {t("ai.send")}
          </button>
          {conversationId && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                storeConversation(null);
                setConversationId(null);
              }}
            >
              {t("ai.newConversation")}
            </button>
          )}
        </div>
        <p className="muted small">{t("ai.boundaries")}</p>
      </form>
    </div>
  );
}
