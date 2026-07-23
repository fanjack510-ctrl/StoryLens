import type { CapabilityPresentation } from "../../services/capability/presentation";
import "./capability.css";

export type CapabilityReasonPanelProps = {
  presentation: CapabilityPresentation;
};

export function CapabilityReasonPanel({ presentation }: CapabilityReasonPanelProps) {
  return (
    <div
      className="capability-reason capability-root"
      data-testid="capability-reason-panel"
      data-state={presentation.state}
      role="status"
      aria-live="polite"
    >
      <p className="capability-reason__label">{presentation.label}</p>
      <p className="capability-reason__message">{presentation.message}</p>
    </div>
  );
}
