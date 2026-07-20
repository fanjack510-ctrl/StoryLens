import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  bootstrapDesktopRuntime,
  isTauriRuntime,
  listenBackendEvents,
  type BackendUiStatus,
} from "../../services/desktopRuntime";
import { checkForAppUpdate, type UpdateCheckResult } from "../../services/updaterService";
import { trackAppLaunchedOncePerSession } from "../../services/telemetry/telemetryRuntime";
import { UpdateAvailableDialog } from "./UpdateAvailableDialog";
import { Button } from "../ui/Button";

export function DesktopBootstrap({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<BackendUiStatus>({ state: "starting" });
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [updateInfo, setUpdateInfo] = useState<UpdateCheckResult | null>(null);
  const [dismissedUpdate, setDismissedUpdate] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [bootKey, setBootKey] = useState(0);

  const retryBootstrap = useCallback(() => {
    setRuntimeError(null);
    setDetailsOpen(false);
    setStatus({ state: "starting" });
    setBootKey((k) => k + 1);
  }, []);

  const exitApp = useCallback(async () => {
    if (!isTauriRuntime()) {
      window.close();
      return;
    }
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().close();
    } catch {
      window.close();
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let unlisten: (() => void) | undefined;

    (async () => {
      // DEV / UI-audit only: force bootstrap screens without touching production paths.
      if (import.meta.env.DEV) {
        const force = sessionStorage.getItem("storylens.uiAudit.forceBootstrap");
        if (force === "starting") {
          setStatus({ state: "starting" });
          return;
        }
        if (force === "failed") {
          setStatus({
            state: "failed",
            message: "审计模拟：本地分析服务未能启动（Sidecar 连接失败）。",
          });
          return;
        }
      }

      const result = await bootstrapDesktopRuntime((next) => {
        if (!cancelled) setStatus(next);
      });
      if (cancelled) return;
      setStatus(result);
      if (result.state === "failed") {
        setRuntimeError(result.message);
      }

      unlisten = await listenBackendEvents((message) => {
        if (!cancelled) setRuntimeError(message);
      });

      if (result.state === "ready" || result.state === "browser_dev") {
        trackAppLaunchedOncePerSession();
        const update = await checkForAppUpdate(false);
        if (!cancelled && update.kind === "available") {
          setUpdateInfo(update);
        }
      }
    })();

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [bootKey]);

  if (status.state === "starting") {
    return (
      <div className="desktop-bootstrap" data-testid="desktop-bootstrap-starting" data-theme="light">
        <div className="desktop-bootstrap-brand" aria-hidden="true">
          <span className="brand-mark">SL</span>
        </div>
        <h1 className="sl-page-title">正在启动 StoryLens</h1>
        <p>正在连接本地分析服务，通常只需几秒钟</p>
        <div className="desktop-bootstrap-progress" role="status" aria-label="正在启动">
          <span className="desktop-bootstrap-spinner" />
        </div>
      </div>
    );
  }

  if (status.state === "failed") {
    return (
      <div
        className="desktop-bootstrap desktop-bootstrap-error"
        data-testid="desktop-bootstrap-error"
        data-theme="light"
      >
        <div className="desktop-bootstrap-brand" aria-hidden="true">
          <span className="brand-mark">SL</span>
        </div>
        <h1 className="sl-page-title">StoryLens 无法启动</h1>
        <p>本地分析服务未能正常启动。</p>
        <p className="muted">你的书籍和已有分析数据不会受到影响。</p>
        <div className="desktop-bootstrap-actions">
          <Button
            variant="primary"
            data-testid="desktop-bootstrap-retry"
            onClick={retryBootstrap}
          >
            重新启动
          </Button>
          <Button variant="secondary" data-testid="desktop-bootstrap-exit" onClick={() => void exitApp()}>
            退出 StoryLens
          </Button>
        </div>
        <details
          className="desktop-bootstrap-details"
          open={detailsOpen}
          onToggle={(e) => setDetailsOpen((e.target as HTMLDetailsElement).open)}
        >
          <summary>查看详情</summary>
          <p role="status">{status.message}</p>
          <p className="muted">详细信息已写入本机日志目录（用户数据下的 logs 文件夹）。</p>
        </details>
      </div>
    );
  }

  return (
    <>
      {runtimeError && (
        <div className="desktop-runtime-banner" role="alert" data-testid="desktop-runtime-banner">
          <span>{runtimeError}</span>
          <button type="button" onClick={() => setRuntimeError(null)}>
            知道了
          </button>
        </div>
      )}
      {children}
      {updateInfo?.kind === "available" && !dismissedUpdate && (
        <UpdateAvailableDialog
          currentVersion={updateInfo.currentVersion}
          latestVersion={updateInfo.latestVersion}
          body={updateInfo.body}
          onLater={() => setDismissedUpdate(true)}
          onUpdate={async () => {
            try {
              await updateInfo.downloadAndInstall();
            } catch {
              setRuntimeError("更新安装失败。这不影响本地分析，请稍后在设置中重试。");
              setDismissedUpdate(true);
            }
          }}
        />
      )}
    </>
  );
}
