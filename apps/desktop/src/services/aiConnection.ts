/** 设置页那张状态卡的数据源。
 *
 *  取代 `/desktop/ai-setup/recommended-qwen`。那一支把服务商写死成阿里云，于是一个用
 *  DeepSeek 的人会读到一张混着两家的卡：状态和「配置已更改，需要重新验证」来自阿里云的
 *  指纹比对，模型名却来自全局验证快照。指纹永远对不上，那句提示因此**验证多少次都消不掉**。
 *
 *  这里只有一个来源：当前活跃服务商。
 */
import { api } from "./apiClient";

export type AiConnectionStatus = {
  provider_name: string;
  display_name: string;
  model: string;
  credential_configured: boolean;
  provider_enabled: boolean;
  cloud_enabled: boolean;
  cloud_body_consent: boolean;
  provider_eligible: boolean;
  analysis_ready: boolean;
  /** unconfigured | disabled | disconnected | partial | connected */
  connection_state: string;
  /** NOT_CONFIGURED | CONFIGURED_NOT_VERIFIED | VERIFIED | CONFIG_CHANGED | VERIFICATION_FAILED | CONSENT_REQUIRED | READY */
  ui_state: string;
  ui_label: string;
  ui_reason: string;
  validated_at: string | null;
  validated_at_display: string | null;
  validated_model: string | null;
  blockers: string[];
  /** 后端翻译好的人话。客户端不再自己拼错误文案（INV-P4）。 */
  blocker_labels: string[];
  blocker_guidance: string | null;
};

export function fetchAiConnection(): Promise<AiConnectionStatus> {
  return api<AiConnectionStatus>("/api/v1/desktop/ai-connection");
}
