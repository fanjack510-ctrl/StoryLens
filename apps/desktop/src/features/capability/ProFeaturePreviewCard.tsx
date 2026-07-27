import { Button } from "../../components/ui/Button";
import type { CapabilityPresentation } from "../../services/capability/presentation";
import { CapabilityStatusBadge } from "./CapabilityStatusBadge";
import "./capability.css";

export type ProFeaturePreviewCardProps = {
  presentation: CapabilityPresentation;
  onPreview?: () => void;
  onUpgrade?: () => void;
};

/**
 * Preview card distinguishing preview vs available.
 * Foundation capability is never shown as paywalled.
 */
export function ProFeaturePreviewCard({
  presentation,
  onPreview,
  onUpgrade,
}: ProFeaturePreviewCardProps) {
  return (
    <article
      className="capability-preview-card capability-root"
      data-testid="pro-feature-preview-card"
      data-state={presentation.state}
      data-capability={presentation.capabilityKey}
      tabIndex={0}
      aria-disabled={presentation.disabled || undefined}
    >
      <header className="capability-gate__header">
        <h3 className="capability-preview-card__title">{presentation.label}</h3>
        <CapabilityStatusBadge
          capabilityKey={presentation.capabilityKey}
          state={presentation.state}
        />
      </header>
      <p className="capability-preview-card__message">{presentation.message}</p>
      {(presentation.showPreviewAction || presentation.showUpgradeAction) && (
        <div className="capability-gate__actions">
          {presentation.showPreviewAction ? (
            <Button
              type="button"
              variant="secondary"
              data-testid="capability-preview-action"
              onClick={onPreview}
            >
              查看预览
            </Button>
          ) : null}
          {presentation.showUpgradeAction ? (
            <Button
              type="button"
              variant="primary"
              data-testid="capability-upgrade-action"
              onClick={onUpgrade}
            >
              查看授权说明
            </Button>
          ) : null}
        </div>
      )}
    </article>
  );
}
