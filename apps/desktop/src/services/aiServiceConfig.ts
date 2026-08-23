/** AI 相关查询的失效通知，以及运行时环境画像的类型。
 *
 *  这里原本还装着一条只为通义千问准备的一键配置路径（`recommended-qwen`）：状态、保存、
 *  验证、修复各一个函数。它和通用的服务商配置并存，于是设置页上出现了两个 API Key 输入框、
 *  两个同意勾选、两组按钮，而「AI服务」那一栏写死显示阿里云——哪怕当前用的是 DeepSeek。
 *
 *  那条路径已经整条删除。状态改由 `aiConnection.ts` 提供（按当前服务商算），保存与验证
 *  走通用的 `providersApi`。
 */
import type { QueryClient } from "@tanstack/react-query";

export type ConfigRuntimeProfile = {
  runtime_mode: "browser_dev" | "desktop_dev" | "packaged" | "browser_local_production";
  app_env: "development" | "production";
  is_frozen?: boolean;
  data_directory: string;
  database_path: string;
  isolates_sqlite_from_packaged?: boolean;
  packaged_data_directory_hint?: string | null;
  credential_store: {
    type: string;
    available: boolean;
    machine_scoped?: boolean;
    returns_secret_to_api?: boolean;
    shares_with_packaged?: boolean;
    desktop_parity?: boolean;
  };
  user_message: string;
};

/** 改完 AI 配置之后，把所有依赖它的查询打成过期。
 *
 *  少一条就会有一处界面继续拿旧状态渲染——比如全书分析的准备面板还以为服务商没连上。
 */
export async function invalidateAiQueries(qc: QueryClient) {
  await Promise.all([
    qc.invalidateQueries({ queryKey: ["providers"] }),
    qc.invalidateQueries({ queryKey: ["cloud"] }),
    qc.invalidateQueries({ queryKey: ["cloud-usage"] }),
    qc.invalidateQueries({ queryKey: ["cloud-budget"] }),
    qc.invalidateQueries({ queryKey: ["provider-config"] }),
    qc.invalidateQueries({ queryKey: ["ai-connection"] }),
    qc.invalidateQueries({ queryKey: ["active-cloud-provider"] }),
    qc.invalidateQueries({ queryKey: ["analysis-execution-plan"] }),
  ]);
}
