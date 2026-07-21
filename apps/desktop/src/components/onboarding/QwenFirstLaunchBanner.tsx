import { Link } from "react-router-dom";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { providersApi } from "../../services/providersApi";
import { DEFAULT_AI_SERVICE_ID, buildAiServiceViewModel } from "../../services/aiServiceViewModel";
import { settingsApi } from "../../services/settingsApi";

import { useOnboardingStore } from "../../stores/onboardingStore";
import { Button } from "../ui/Button";

/** Empty-library entry when AI is not configured (after onboarding). */
export function QwenFirstLaunchBanner() {
  const onboardingStatus = useOnboardingStore((s) => s.status);
  const [later, setLater] = useState(false);
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

  if (onboardingStatus === "pending" || configuration.isLoading || view.apiKeyConfigured || later) {
    return null;
  }

  return (
    <aside className="qwen-first-launch-banner status-card" data-testid="qwen-first-launch-banner">
      <div>
        <h2>尚未连接 AI 服务</h2>
        <p>建议先配置阿里云百炼，完成后再导入小说并开始分析。</p>
      </div>
      <div className="qwen-first-launch-actions">
        <Link
          className="primary"
          to="/settings?tab=ai&focus=api_key"
          data-testid="qwen-first-launch-configure"
        >
          配置阿里云百炼
        </Link>
        <Button variant="ghost" data-testid="qwen-first-launch-later" onClick={() => setLater(true)}>
          稍后
        </Button>
      </div>
    </aside>
  );
}
