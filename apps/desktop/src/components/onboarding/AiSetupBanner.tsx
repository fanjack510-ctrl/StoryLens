import { Link } from "react-router-dom";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAiConnection } from "../../services/aiConnection";
import { useOnboardingStore } from "../../stores/onboardingStore";
import { Button } from "../ui/Button";

/** 书库为空、AI 还没连上时的入口。
 *
 *  以前叫 `QwenFirstLaunchBanner`，写死「建议先配置阿里云百炼」，判断「配好了没有」用的也是
 *  阿里云那一行。于是一个把 DeepSeek 配得好好的人，回到书库仍然被告知「尚未连接 AI 服务」，
 *  按钮还劝他去配另一家。
 *
 *  现在只问一件事：**当前服务商**连上了没有。文案也不再替用户挑厂商。
 */
export function AiSetupBanner() {
  const onboardingStatus = useOnboardingStore((s) => s.status);
  const [later, setLater] = useState(false);
  const connection = useQuery({ queryKey: ["ai-connection"], queryFn: fetchAiConnection });

  if (
    onboardingStatus === "pending" ||
    connection.isLoading ||
    connection.data?.credential_configured ||
    later
  ) {
    return null;
  }

  return (
    <aside className="qwen-first-launch-banner status-card" data-testid="ai-setup-banner">
      <div>
        <h2>尚未连接 AI 服务</h2>
        <p>先连上一个 AI 服务商，再导入小说并开始分析。</p>
      </div>
      <div className="qwen-first-launch-actions">
        <Link className="primary" to="/settings?tab=ai&focus=api_key" data-testid="ai-setup-configure">
          去连接
        </Link>
        <Button variant="ghost" data-testid="ai-setup-later" onClick={() => setLater(true)}>
          稍后
        </Button>
      </div>
    </aside>
  );
}
