import { useEffect, useState } from "react";
import { Dialog } from "../ui/Dialog";
import { Button } from "../ui/Button";
import {
  confirmInstall,
  deferInstall,
  dismissAvailableUpdate,
  getUpdaterSnapshot,
  relaunchToApplyUpdate,
  resetUpdaterFailure,
  startDownload,
  subscribeUpdater,
  type UpdaterSnapshot,
} from "../../services/updaterService";

type Props = {
  /** When false, dialog is hidden but settings can still show status. */
  open?: boolean;
  onClose?: () => void;
};

export function UpdateAvailableDialog({ open = true, onClose }: Props) {
  const [snap, setSnap] = useState<UpdaterSnapshot>(() => getUpdaterSnapshot());
  const [busy, setBusy] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);

  useEffect(() => subscribeUpdater(setSnap), []);

  if (!open) return null;

  const show =
    snap.phase === "available" ||
    snap.phase === "downloading" ||
    snap.phase === "downloaded" ||
    snap.phase === "installing" ||
    snap.phase === "restart_required" ||
    snap.phase === "failed";

  if (!show) return null;

  const title =
    snap.phase === "downloading"
      ? "正在下载更新"
      : snap.phase === "downloaded"
        ? "更新已下载"
        : snap.phase === "installing"
          ? "正在安装更新"
          : snap.phase === "restart_required"
            ? "需要重启以完成更新"
            : snap.phase === "failed"
              ? "更新失败"
              : `发现新版本 ${snap.latestVersion ?? ""}`;

  const onLater = () => {
    dismissAvailableUpdate();
    onClose?.();
  };

  const onStartDownload = async () => {
    setBusy(true);
    try {
      await startDownload();
    } finally {
      setBusy(false);
    }
  };

  const onDeferInstall = () => {
    deferInstall();
    onClose?.();
  };

  const onInstallNow = async () => {
    setBusy(true);
    try {
      const next = await confirmInstall();
      if (next.phase === "restart_required") {
        await relaunchToApplyUpdate();
      }
    } catch {
      /* error already in snapshot */
    } finally {
      setBusy(false);
    }
  };

  const onRelaunch = async () => {
    setBusy(true);
    try {
      await relaunchToApplyUpdate();
    } catch {
      setBusy(false);
    }
  };

  const footer = (() => {
    if (snap.phase === "available") {
      return (
        <>
          <Button variant="secondary" data-testid="update-later" onClick={onLater}>
            稍后再说
          </Button>
          <Button
            variant="primary"
            data-testid="update-now"
            disabled={busy}
            onClick={() => void onStartDownload()}
          >
            立即更新
          </Button>
        </>
      );
    }
    if (snap.phase === "downloading") {
      return (
        <Button variant="secondary" disabled>
          下载中…
        </Button>
      );
    }
    if (snap.phase === "downloaded") {
      return (
        <>
          <Button variant="secondary" data-testid="update-defer-install" onClick={onDeferInstall}>
            稍后安装
          </Button>
          <Button
            variant="primary"
            data-testid="update-install-now"
            disabled={busy}
            onClick={() => void onInstallNow()}
          >
            立即重启并安装
          </Button>
        </>
      );
    }
    if (snap.phase === "installing") {
      return (
        <Button variant="secondary" disabled>
          安装中…
        </Button>
      );
    }
    if (snap.phase === "restart_required") {
      return (
        <>
          <Button variant="secondary" data-testid="update-restart-later" onClick={() => onClose?.()}>
            稍后重启
          </Button>
          <Button
            variant="primary"
            data-testid="update-relaunch"
            disabled={busy}
            onClick={() => void onRelaunch()}
          >
            立即重启
          </Button>
        </>
      );
    }
    // failed
    return (
      <>
        <Button
          variant="secondary"
          data-testid="update-dismiss-error"
          onClick={() => {
            resetUpdaterFailure();
            onClose?.();
          }}
        >
          关闭
        </Button>
        <Button
          variant="primary"
          data-testid="update-retry"
          disabled={busy}
          onClick={() => {
            resetUpdaterFailure();
            void onStartDownload();
          }}
        >
          重试下载
        </Button>
      </>
    );
  })();

  return (
    <Dialog
      title={title}
      data-testid="update-available-dialog"
      onClose={snap.phase === "downloading" || snap.phase === "installing" ? undefined : onLater}
      className="update-dialog"
      footer={footer}
    >
      <p>
        当前版本：<strong>{snap.currentVersion || "—"}</strong>
        <br />
        新版本：<strong>{snap.latestVersion || "—"}</strong>
      </p>

      {snap.phase === "available" && (
        <div className="update-dialog-body">
          <h3>本次更新</h3>
          <pre>{snap.releaseNotes || "修复问题并改进稳定性。"}</pre>
        </div>
      )}

      {snap.phase === "downloading" && snap.progress && (
        <div className="update-dialog-progress" data-testid="update-download-progress">
          <div
            className="update-dialog-progress-bar"
            style={{ width: `${snap.progress.percent ?? 5}%` }}
          />
          <p className="muted">{snap.message}</p>
        </div>
      )}

      {(snap.phase === "downloaded" || snap.phase === "restart_required") && (
        <p role="status" data-testid="update-save-work-hint">
          安装或重启前请先保存正在编辑的内容。更新不会删除你的书籍与分析数据。
        </p>
      )}

      {snap.phase === "failed" && (
        <p role="alert">{snap.message}</p>
      )}

      {snap.message && snap.phase !== "failed" && snap.phase !== "available" && (
        <p className="muted">{snap.message}</p>
      )}

      {snap.technicalDetail && (
        <details
          className="update-dialog-tech"
          open={detailsOpen}
          onToggle={(e) => setDetailsOpen((e.target as HTMLDetailsElement).open)}
        >
          <summary>技术详情</summary>
          <pre data-testid="update-technical-detail">{snap.technicalDetail}</pre>
        </details>
      )}
    </Dialog>
  );
}
