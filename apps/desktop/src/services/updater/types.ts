export type UpdaterPhase =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "downloaded"
  | "installing"
  | "restart_required"
  | "up_to_date"
  | "failed"
  | "dismissed";

export type DownloadProgress = {
  downloadedBytes: number;
  totalBytes: number | null;
  percent: number | null;
};

export type UpdaterSnapshot = {
  phase: UpdaterPhase;
  currentVersion: string;
  latestVersion: string | null;
  releaseNotes: string;
  progress: DownloadProgress | null;
  /** User-facing short message */
  message: string;
  /** Raw updater / network error for technical details only */
  technicalDetail: string | null;
  lastCheckAt: string | null;
  channel: "stable" | "staging";
};

export const INITIAL_UPDATER_SNAPSHOT: UpdaterSnapshot = {
  phase: "idle",
  currentVersion: "",
  latestVersion: null,
  releaseNotes: "",
  progress: null,
  message: "",
  technicalDetail: null,
  lastCheckAt: null,
  channel: "stable",
};

export function phaseLabel(phase: UpdaterPhase): string {
  switch (phase) {
    case "idle":
      return "空闲";
    case "checking":
      return "正在检查";
    case "available":
      return "有新版本";
    case "downloading":
      return "正在下载";
    case "downloaded":
      return "已下载，待安装";
    case "installing":
      return "正在安装";
    case "restart_required":
      return "需要重启";
    case "up_to_date":
      return "已是最新";
    case "failed":
      return "失败";
    case "dismissed":
      return "已稍后提醒";
    default:
      return phase;
  }
}
