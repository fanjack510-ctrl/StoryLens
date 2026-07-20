import { useEffect, useState, type ReactNode } from "react";
import {
  bootstrapDesktopRuntime,
  listenBackendEvents,
  type BackendUiStatus,
} from "../../services/desktopRuntime";
import { checkForAppUpdate, type UpdateCheckResult } from "../../services/updaterService";
import { trackAppLaunchedOncePerSession } from "../../services/telemetry/telemetryRuntime";
import { UpdateAvailableDialog } from "./UpdateAvailableDialog";

export function DesktopBootstrap({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<BackendUiStatus>({ state: "starting" });
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [updateInfo, setUpdateInfo] = useState<UpdateCheckResult | null>(null);
  const [dismissedUpdate, setDismissedUpdate] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let unlisten: (() => void) | undefined;

    (async () => {
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
  }, []);

  if (status.state === "starting") {
    return (
      <div className="desktop-bootstrap" data-testid="desktop-bootstrap-starting">
        <h1>StoryLens</h1>
        <p>正在启动本地分析服务，请稍候…</p>
      </div>
    );
  }

  if (status.state === "failed") {
    return (
      <div className="desktop-bootstrap desktop-bootstrap-error" data-testid="desktop-bootstrap-error">
        <h1>StoryLens 无法启动</h1>
        <p>{status.message}</p>
        <p className="muted">详细信息已写入本机日志（%LOCALAPPDATA%\\StoryLens\\logs）。</p>
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
