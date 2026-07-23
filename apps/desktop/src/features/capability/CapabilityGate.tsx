import type { KeyboardEvent, ReactNode } from "react";
import { Button } from "../../components/ui/Button";
import type { CapabilityPresentation } from "../../services/capability/presentation";
import { CapabilityReasonPanel } from "./CapabilityReasonPanel";
import { CapabilityStatusBadge } from "./CapabilityStatusBadge";
import "./capability.css";

export type CapabilityGateProps = {
  presentation: CapabilityPresentation;
  children?: ReactNode;
  /** When true and disabled, still render children dimmed (never silent-hide only). */
  showChildrenWhenBlocked?: boolean;
  onPreview?: () => void;
  onUpgrade?: () => void;
  onActivate?: () => void;
};

/**
 * CapabilityGate must show deny/preview reason — never only hide content.
 */
export function CapabilityGate({
  presentation,
  children,
  showChildrenWhenBlocked = true,
  onPreview,
  onUpgrade,
  onActivate,
}: CapabilityGateProps) {
  const blocked = presentation.disabled;
  const available = presentation.state === "available";

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    if (blocked) {
      event.preventDefault();
      return;
    }
    onActivate?.();
  };

  return (
    <section
      className="capability-gate capability-root"
      data-testid="capability-gate"
      data-capability={presentation.capabilityKey}
      data-state={presentation.state}
      data-disabled={blocked ? "true" : "false"}
      tabIndex={0}
      role="group"
      aria-disabled={blocked || undefined}
      aria-label={`${presentation.label}：${presentation.message}`}
      onKeyDown={onKeyDown}
    >
      <header className="capability-gate__header">
        <h3 className="capability-gate__title">{presentation.label}</h3>
        <CapabilityStatusBadge
          capabilityKey={presentation.capabilityKey}
          state={presentation.state}
        />
      </header>

      {!available ? <CapabilityReasonPanel presentation={presentation} /> : null}

      {available ? (
        <p className="capability-gate__body">{presentation.message}</p>
      ) : null}

      {(presentation.showPreviewAction || presentation.showUpgradeAction) && (
        <div className="capability-gate__actions">
          {presentation.showPreviewAction ? (
            <Button
              type="button"
              variant="secondary"
              data-testid="capability-gate-preview"
              onClick={onPreview}
            >
              查看预览
            </Button>
          ) : null}
          {presentation.showUpgradeAction ? (
            <Button
              type="button"
              variant="primary"
              data-testid="capability-gate-upgrade"
              onClick={onUpgrade}
            >
              查看授权说明
            </Button>
          ) : null}
        </div>
      )}

      {children && (available || showChildrenWhenBlocked) ? (
        <div
          className="capability-gate__children"
          data-blocked={blocked && !available ? "true" : "false"}
          data-testid="capability-gate-children"
        >
          {children}
        </div>
      ) : null}
    </section>
  );
}
