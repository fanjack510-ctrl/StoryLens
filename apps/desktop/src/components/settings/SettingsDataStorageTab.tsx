import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { settingsApi } from "../../services/settingsApi";
import { Loading } from "../common/States";

export function SettingsDataStorageTab() {
  const [message, setMessage] = useState("");
  const diagnostics = useQuery({ queryKey: ["diagnostics"], queryFn: settingsApi.diagnostics });

  const dataDir = diagnostics.data?.data_directory as string | undefined;

  const copyPath = async () => {
    if (!dataDir) {
      setMessage("暂时无法读取数据目录，请稍后重试。");
      return;
    }
    try {
      await navigator.clipboard?.writeText(dataDir);
      setMessage("数据目录路径已复制，可在资源管理器中粘贴打开。");
    } catch {
      setMessage(`数据目录：${dataDir}`);
    }
  };

  if (diagnostics.isLoading) {
    return (
      <article className="settings-panel">
        <Loading />
      </article>
    );
  }

  return (
    <article className="settings-panel" data-testid="settings-panel-data">
      <header className="settings-panel-header">
        <h2>数据与存储</h2>
        <p>书库与分析结果保存在本机，不会上传到 StoryLens 服务器。</p>
      </header>

      <label className="settings-field">
        <span>当前数据目录</span>
        <input readOnly aria-label="当前数据目录" value={dataDir || "读取中…"} />
      </label>

      <div className="settings-actions">
        <button type="button" data-testid="open-data-dir" onClick={() => void copyPath()}>
          打开数据目录
        </button>
        <button type="button" disabled title="尚未实现" data-testid="backup-library">
          备份书库（尚未实现）
        </button>
        <button type="button" disabled title="尚未实现" data-testid="restore-library">
          恢复书库（尚未实现）
        </button>
        <button type="button" disabled title="尚未实现" data-testid="clear-cache">
          清理缓存（尚未实现）
        </button>
      </div>

      <p className="hint" data-testid="log-space-hint">
        日志占用空间：尚未统计（日志位于数据目录下的 logs 文件夹）。
      </p>

      {message && <p role="status">{message}</p>}
    </article>
  );
}
