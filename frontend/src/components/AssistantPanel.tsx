import { useI18n } from "../i18n";
import { Chat } from "./Chat";

/** Contextual assistant panel (full screen on phones). It shares the AI Financial Workspace
 * conversation and reports the real connection state; no reply is ever simulated. */
export function AssistantPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  return (
    <aside id="assistant" className="assistant" aria-label={t("assistant.title")} hidden={!open}>
      <header className="assistant-header">
        <h2>{t("assistant.title")}</h2>
        <button type="button" className="btn btn-ghost" onClick={onClose}>
          {t("assistant.close")}
        </button>
      </header>
      {open && <Chat compact />}
    </aside>
  );
}
