import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { providersApi } from "../../services/providersApi";
import { DEFAULT_AI_SERVICE_ID, buildAiServiceViewModel } from "../../services/aiServiceViewModel";
import { settingsApi } from "../../services/settingsApi";

/** Welcome / empty-library entry that deep-links into Qwen API Key setup. */
export function QwenFirstLaunchBanner() {
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

  if (configuration.isLoading || view.apiKeyConfigured) return null;

  return (
    <aside className="qwen-first-launch-banner" data-testid="qwen-first-launch-banner">
      <div>
        <h2>欢迎使用 StoryLens</h2>
        <p>
          V1.0 普通模式正式支持阿里云百炼 · Qwen。请先配置你自己的 API Key；
          费用由你的阿里云账户承担，StoryLens 不提供云端账号。
        </p>
      </div>
      <Link
        className="primary"
        to="/settings?tab=ai&focus=api_key"
        data-testid="qwen-first-launch-configure"
      >
        配置阿里云百炼 · Qwen
      </Link>
    </aside>
  );
}
