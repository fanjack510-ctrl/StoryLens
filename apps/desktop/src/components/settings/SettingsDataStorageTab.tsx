import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { settingsApi } from "../../services/settingsApi";
import { Loading } from "../common/States";
import "./settings.css";

function truncatePath(path: string, max = 48): string {
  if (path.length <= max) return path;
  const keep = Math.floor((max - 1) / 2);
  return `${path.slice(0, keep)}…${path.slice(-keep)}`;
}

export function SettingsDataStorageTab() {
  const [message, setMessage] = useState("");
  const diagnostics = useQuery({ queryKey: ["diagnostics"], queryFn: settingsApi.diagnostics });

  const dataDir = diagnostics.data?.data_directory as string | undefined;
  const dbPath =
    (diagnostics.data?.database_path as string | undefined) ||
    (diagnostics.data?.sqlite_path as string | undefined) ||
    (dataDir ? `${dataDir}\\storylens.db` : undefined);

  const copyPath = async (path?: string, label = "路径") => {
    if (!path) {
      setMessage(`暂时无法读取${label}，请稍后重试。`);
      return;
    }
    try {
      await navigator.clipboard?.writeText(path);
      setMessage(`${label}已复制，可在资源管理器中粘贴打开。`);
    } catch {
      setMessage(`${label}：${path}`);
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
    <article className="settings-panel settings-module" data-testid="settings-panel-data">
      <header className="settings-panel-header">
        <h2>数据与存储</h2>
        <p>书库与分析结果保存在本机，不会上传到 StoryLens 服务器。</p>
      </header>

      <section className="settings-zone" data-testid="data-dir-zone">
        <h3>数据目录</h3>
        <p className="zone-hint">书库、日志与本地配置所在位置。</p>
        <div className="settings-path-row settings-field">
          <span>当前数据目录</span>
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
            data-testid="open-data-dir"
            onClick={() => void copyPath(dataDir, "数据目录路径")}
          >
            打开数据目录
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

      <section className="settings-zone" data-testid="data-db-zone">
        <h3>数据库</h3>
        <p className="zone-hint">本地 SQLite 存储分析与书库元数据。</p>
        <div className="settings-path-row settings-field">
          <span>数据库文件</span>
          <div
            className="settings-path-value"
            title={dbPath || undefined}
            data-testid="data-db-path"
          >
            {dbPath ? truncatePath(dbPath) : "—"}
          </div>
        </div>
        <p className="hint" data-testid="log-space-hint">
          日志占用空间：尚未统计（日志位于数据目录下的 logs 文件夹）。
        </p>
      </section>

      <section className="settings-zone" data-testid="data-upload-zone">
        <h3>上传与导入</h3>
        <p className="zone-hint">小说文本导入到本机书库；不会上传到 StoryLens 云端。</p>
        <div className="settings-actions">
          <button type="button" disabled title="请从书库页导入" data-testid="data-import-hint">
            从书库导入（请前往书库）
          </button>
        </div>
      </section>

      <section className="settings-zone" data-testid="data-export-zone">
        <h3>导出与备份</h3>
        <p className="zone-hint">备份与恢复能力尚未实现，按钮保持禁用以避免误操作。</p>
        <div className="settings-actions">
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
      </section>

      {message && <p role="status">{message}</p>}
    </article>
  );
}
