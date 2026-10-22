import { Card, StatusBadge } from "../components/ui";
import { useI18n } from "../i18n";
import type { Section } from "../router";

/** Honest placeholder: describes what is planned and offers no buttons that pretend to work. */
export function SectionPlaceholder({ section }: { section: Section }) {
  const { t } = useI18n();
  return (
    <>
      <div className="page-heading">
        <h1 tabIndex={-1}>{t(`nav.${section}`)}</h1>
        <StatusBadge tone="warning">{t("section.inDevelopment")}</StatusBadge>
      </div>
      <PlannedCard section={section} />
    </>
  );
}

export function PlannedCard({ section }: { section: Section }) {
  const { t } = useI18n();
  return (
    <Card>
      <p>{t("section.planned")}</p>
      <p>{t(`planned.${section}`)}</p>
      <p className="muted">{t("section.noActions")}</p>
    </Card>
  );
}
