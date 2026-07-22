import { useTelemetryStore } from "../../stores/telemetry";
import { Button } from "../ui/Button";

/** Non-blocking telemetry invite shown once after onboarding when consent is UNKNOWN. */
export function TelemetryInviteCard() {
  const consent = useTelemetryStore((s) => s.consent);
  const setEnabled = useTelemetryStore((s) => s.setAnonymousTelemetryEnabled);

  if (consent !== "UNKNOWN") {
    return null;
  }

  return (
    <aside
      className="telemetry-invite-card"
      data-testid="telemetry-invite-card"
      aria-label="帮助改进 StoryLens"
    >
      <div className="telemetry-invite-card__copy">
        <h3>帮助改进 StoryLens</h3>
        <p>
          允许发送应用版本、系统类型和匿名功能使用次数。不包含书籍正文、分析结果、文件路径或API Key。
        </p>
      </div>
      <div className="telemetry-invite-card__actions">
        <Button
          variant="secondary"
          data-testid="telemetry-invite-decline"
          onClick={() => setEnabled(false)}
        >
          暂不发送
        </Button>
        <Button
          variant="secondary"
          data-testid="telemetry-invite-accept"
          onClick={() => setEnabled(true)}
        >
          允许发送
        </Button>
      </div>
    </aside>
  );
}
