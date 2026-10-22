import { api, CALENDAR_URL } from "../api";
import { ErrorNotice, label, useLoad } from "./finance";
import { Card, Money, StatusBadge } from "./ui";
import { useI18n } from "../i18n";

/** Deadlines in the next two weeks, computed when the page is opened. There is no background
 * notification system; the calendar export lets the user add the dates to their own calendar. */
export function DeadlineNotices() {
  const { t, formatDate } = useI18n();
  const { data, error } = useLoad(() => api.notices(), []);
  return (
    <Card
      title={t("notice.title")}
      icon="calendar"
      id="deadlines"
      actions={
        <a className="btn btn-ghost btn-small" href={CALENDAR_URL} download>
          {t("notice.calendar")}
        </a>
      }
    >
      <ErrorNotice error={error} />
      {data &&
        (data.notices.length === 0 ? (
          <p className="muted">{t("notice.none", { days: data.window_days })}</p>
        ) : (
          <ul className="event-list">
            {data.notices.map((n) => (
              <li key={`${n.kind}-${n.id}`}>
                <span>
                  <StatusBadge tone={n.state === "overdue" ? "danger" : n.state === "today" ? "warning" : "info"}>
                    {n.state === "soon" ? t("notice.inDays", { days: n.days }) : label(t, "notice.state", n.state)}
                  </StatusBadge>{" "}
                  {label(t, "notice.kind", n.kind)}: <bdi>{n.title}</bdi>
                  {n.amount && n.currency && (
                    <>
                      {" "}
                      <Money amount={n.amount} currency={n.currency} />
                    </>
                  )}
                </span>
                <time className="muted small" dateTime={n.date}>
                  {formatDate(n.date)}
                </time>
              </li>
            ))}
          </ul>
        ))}
      <p className="muted small">{t("notice.hint")}</p>
    </Card>
  );
}
