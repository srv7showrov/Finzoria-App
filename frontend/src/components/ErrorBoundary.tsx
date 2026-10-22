import { Component, type ErrorInfo, type ReactNode } from "react";
import { useI18n } from "../i18n";
import { Notice } from "./ui";

/** Keeps a failure in one section from blanking the whole app. It resets when the route
 * changes. Only the error type is logged; no user data. */
export class ErrorBoundary extends Component<{ resetKey: string; children: ReactNode }, { failed: boolean; key: string }> {
  state = { failed: false, key: this.props.resetKey };

  static getDerivedStateFromError(): Partial<{ failed: boolean }> {
    return { failed: true };
  }

  static getDerivedStateFromProps(props: { resetKey: string }, state: { failed: boolean; key: string }) {
    return props.resetKey !== state.key ? { failed: false, key: props.resetKey } : null;
  }

  componentDidCatch(error: Error, _info: ErrorInfo): void {
    console.error("Section failed:", error.name);
  }

  render(): ReactNode {
    return this.state.failed ? <SectionFailed /> : this.props.children;
  }
}

function SectionFailed() {
  const { t } = useI18n();
  return (
    <div className="card status-card section-failed" role="alert">
      <h1 tabIndex={-1}>{t("app.sectionFailedTitle")}</h1>
      <Notice tone="danger">{t("app.sectionFailedText")}</Notice>
      <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
        {t("app.reload")}
      </button>
    </div>
  );
}
