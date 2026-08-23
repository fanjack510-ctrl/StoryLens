/** 「AI 与模型」标签页。
 *
 *  这里以前是 681 行，装着两套并行的服务商配置——通用的一套，和一套只为通义千问写的一键
 *  配置旧路径。现在只剩一层：把深链参数翻译给面板，剩下的都在 `AiConnectionPanel` 里。
 */
import { AiConnectionPanel } from "./AiConnectionPanel";
import "./settings.css";

type Props = {
  autoOpenWizard?: boolean;
  focusField?: "api_key";
};

export function SettingsAiServiceTab({ autoOpenWizard = false, focusField }: Props) {
  return <AiConnectionPanel focusApiKey={autoOpenWizard || focusField === "api_key"} />;
}
