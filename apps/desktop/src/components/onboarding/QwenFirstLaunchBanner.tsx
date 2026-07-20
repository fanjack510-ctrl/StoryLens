import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { providersApi } from "../../services/providersApi";
import { DEFAULT_AI_SERVICE_ID, buildAiServiceViewModel } from "../../services/aiServiceViewModel";
import { settingsApi } from "../../services/settingsApi";

import { useOnboardingStore } from "../../stores/onboardingStore";

/** Empty-library entry when AI is not configured (after onboarding). */
export function QwenFirstLaunchBanner() {
  const onboardingStatus = useOnboardingStore((s) => s.status);
  const cloud = useQuery({ queryKey: ["cloud"], queryFn: settingsApi.cloud });
  const configuration = useQuery({
    queryKey: ["provider-config", DEFAULT_AI_SERVICE_ID],
    queryFn: () => providersApi.configuration(DEFAULT_AI_SERVICE_ID),
  });
  const providers = useQuery({ queryKey: ["providers"], queryFn: providersApi.list });
  const provider = (providers.data || []).find((p) => p.name === DEFAULT_AI_SERVICE_ID) || null;
  const view = buildAiServiceViewModel({
    provider,
    configuration: configuration.data,
    cloudEnabled: cloud.data?.enabled,
  });

  if (onboardingStatus === "pending" || configuration.isLoading || view.apiKeyConfigured) return null;

  return (
    <aside className="qwen-first-launch-banner" data-testid="qwen-first-launch-banner">
      <div>
        <h2>尚未连接 AI 服务</h2>
        <p>导入小说前建议先填写 API Key 并测试连接。也可稍后在设置中完成。</p>
      </div>
      <Link
        className="primary"
        to="/settings?tab=ai&focus=api_key"
        data-testid="qwen-first-launch-configure"
      >
        去设置 AI 服务
      </Link>
    </aside>
  );
}
