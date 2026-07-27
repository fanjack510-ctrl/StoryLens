import { LAB_UI_LABELS } from "../contracts/actions";

export function MockLabBanner() {
  return (
    <aside
      className="wb-mock-lab__banner"
      role="status"
      data-testid="mock-lab-banner"
      aria-live="polite"
    >
      <strong data-testid="mock-non-production-banner">
        {LAB_UI_LABELS.nonProductionBanner}
      </strong>
      <span className="wb-mock-lab__badge" data-testid="mock-badge-banner">
        {LAB_UI_LABELS.mockBadge}
      </span>
    </aside>
  );
}
