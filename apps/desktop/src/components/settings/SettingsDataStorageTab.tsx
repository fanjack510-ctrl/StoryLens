import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { settingsApi } from "../../services/settingsApi";
import { isLocalWebShell, useRuntimeInfo } from "../../services/runtimeCapabilities";
import { useDeveloperModeStore } from "../../stores/developerModeStore";
import { useAdvancedSettingsStore } from "../../stores/advancedSettingsStore";
import { Loading } from "../common/States";
import "./settings.css";

function truncatePath(path: string, max = 48): string {
  if (path.length <= max) return path;
  const keep = Math.floor((max - 1) / 2);
  return `${path.slice(0, keep)}…${path.slice(-keep)}`;
}

export function SettingsDataStorageTab() {
  const [message, setMessage] = useState("");
  const developerMode = useDeveloperModeStore((s) => s.developerMode);
  const showAdvanced = useAdvancedSettingsStore((s) => s.showAdvancedSettings);
  const showTech = developerMode || showAdvanced;
  const diagnostics = useQuery({ queryKey: ["diagnostics"], queryFn: settingsApi.diagnostics });
  const runtime = useRuntimeInfo();
  const webShell = isLocalWebShell(runtime.data);

  const dataDir =
    (runtime.data?.data_directory as string | undefined) ||
    (diagnostics.data?.data_directory as string | undefined);
  const dbPath =
    (runtime.data?.database_path as string | undefined) ||
    (diagnostics.data?.database_path as string | undefined) ||
    (diagnostics.data?.sqlite_path as string | undefined) ||
    (dataDir ? `${dataDir}\\storylens.db` : undefined);
  const logDir =
    (diagnostics.data?.log_directory as string | undefined) ||
    (dataDir ? `${dataDir}\\logs` : undefined);

  const copyPath = async (path?: string, label = "路径") => {
    if (!path) {
      setMessage(`暂时无法读取${label}，请稍后重试。`);
      return;
    }
    try {
      await navigator.clipboard?.writeText(path);
      setMessage(`${label}已复制。`);
    } catch {
      setMessage(`${label}：${path}`);
    }
  };

  const openDataFolder = async () => {
    try {
      const result = await settingsApi.openDataDirectory();
      setMessage(`已请求打开数据文件夹：${result.path}`);
    } catch {
      await copyPath(dataDir, "数据目录路径");
      setMessage((prev) => `${prev}（若未自动打开，请粘贴到资源管理器地址栏。）`);
    }
  };

  if (diagnostics.isLoading && runtime.isLoading) {
    return (
      <article className="settings-panel">
        <Loading />
      </article>
    );
  }

  return (
    <article className="settings-panel settings-module" data-testid="settings-panel-data">
      <header className="settings-panel-header">
        <h2>数据与备份</h2>
        <p>数据保存在本机。</p>
      </header>

      <section className="settings-zone" data-testid="data-runtime-zone">
        <h3>运行方式</h3>
        <p data-testid="data-runtime-mode">
          {webShell ? "本地网页版" : "桌面版"}
        </p>
        <p className="zone-hint muted" data-testid="data-storage-local">
          数据保存：本机
        </p>
      </section>

      <section className="settings-zone" data-testid="data-dir-zone">
        <h3>数据位置</h3>
        <div className="settings-path-row settings-field">
          <span>当前目录</span>
          <div
            className="settings-path-value"
            title={dataDir || undefined}
            aria-label="当前数据目录"
            data-testid="data-dir-path"
          >
            {dataDir ? truncatePath(dataDir) : "读取中…"}
          </div>
        </div>
        <div className="settings-actions">
          <button
            type="button"
            className="primary"
            data-testid="open-data-dir"
            onClick={() => void openDataFolder()}
            title="通过本机 StoryLens 服务打开文件夹"
          >
            打开数据文件夹
          </button>
          <button
            type="button"
            data-testid="copy-data-dir"
            onClick={() => void copyPath(dataDir, "数据目录路径")}
          >
            复制路径
          </button>
        </div>
      </section>

      <section className="settings-zone" data-testid="data-export-zone">
        <h3>备份与恢复</h3>
        <p className="zone-hint muted" data-testid="data-backup-coming-soon">
          备份与恢复功能将在后续版本提供。
        </p>
      </section>

      <details className="settings-fold" data-testid="data-tech-details">
        <summary>技术详情</summary>
        <div className="settings-fold-body" data-testid="data-db-zone">
          <div className="settings-path-row settings-field">
            <span>数据库文件</span>
            <div
              className="settings-path-value"
              title={dbPath || undefined}
              data-testid="data-db-path"
            >
              {dbPath ? truncatePath(dbPath, 64) : "—"}
            </div>
          </div>
          <button
            type="button"
            data-testid="copy-db-path"
            onClick={() => void copyPath(dbPath, "数据库路径")}
          >
            复制数据库路径
          </button>
        </div>
      </details>

      {showTech && (
        <details className="settings-fold" data-testid="data-dev-details">
          <summary>高级数据详情</summary>
          <div className="settings-fold-body">
            <p>数据目录：{dataDir || "—"}</p>
            <p>数据库文件：{dbPath || "—"}</p>
            <p data-testid="log-space-hint">日志目录：{logDir || "—"}</p>
            <p>运行模式：{runtime.data?.runtime_mode || "—"}</p>
            <p>
              当前环境：
              {String((diagnostics.data as { app_env?: string } | undefined)?.app_env || "—")}
            </p>
          </div>
        </details>
      )}

      {message && <p role="status">{message}</p>}
    </article>
  );
}
