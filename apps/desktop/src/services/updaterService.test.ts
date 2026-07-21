import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  __resetUpdaterForTests,
  __setUpdaterSnapshotForTests,
  assertCheckDoesNotDownloadOrInstall,
  checkForAppUpdate,
  confirmInstall,
  defaultUpdaterPolicy,
  dismissAvailableUpdate,
  endpointForChannel,
  getUpdaterSnapshot,
  loadUpdaterPreferences,
  markUpdateDismissed,
  patchUpdaterPreferences,
  shouldShowUpdateDialog,
  startDownload,
  deferInstall,
} from "./updaterService";
import {
  DEFAULT_UPDATER_PREFERENCES,
  saveUpdaterPreferences,
} from "./updater/preferences";
import {
  STABLE_UPDATE_ENDPOINT,
  STAGING_UPDATE_ENDPOINT,
} from "./updater/channels";

describe("updater opt-in policy", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    __resetUpdaterForTests();
    saveUpdaterPreferences({ ...DEFAULT_UPDATER_PREFERENCES });
  });

  afterEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    __resetUpdaterForTests();
  });

  it("defaults: automatic check on, download/install off, stable channel", () => {
    const policy = defaultUpdaterPolicy();
    expect(policy.automatic_check).toBe(true);
    expect(policy.automatic_download).toBe(false);
    expect(policy.automatic_install).toBe(false);
    expect(policy.channel).toBe("stable");
    expect(loadUpdaterPreferences().automatic_download).toBe(false);
    expect(loadUpdaterPreferences().automatic_install).toBe(false);
  });

  it("refuses to persist automatic_download / automatic_install as true", () => {
    const next = patchUpdaterPreferences({
      automatic_download: true as unknown as false,
      automatic_install: true as unknown as false,
    });
    expect(next.automatic_download).toBe(false);
    expect(next.automatic_install).toBe(false);
    expect(() => assertCheckDoesNotDownloadOrInstall(next)).not.toThrow();
  });

  it("keeps staging and stable endpoints isolated", () => {
    expect(endpointForChannel("stable")).toBe(STABLE_UPDATE_ENDPOINT);
    expect(endpointForChannel("staging")).toBe(STAGING_UPDATE_ENDPOINT);
    expect(endpointForChannel("stable")).not.toBe(endpointForChannel("staging"));
    expect(endpointForChannel("stable")).toContain("latest/download/latest.json");
    expect(endpointForChannel("staging")).toContain("/staging/");
  });

  it("forces stable channel when internal test mode is off", () => {
    const next = patchUpdaterPreferences({
      internal_test_mode: false,
      channel: "staging",
    });
    expect(next.channel).toBe("stable");
  });

  it("dismissed update still counts as available in preferences", () => {
    const prefs = markUpdateDismissed("9.9.9", 24);
    expect(prefs.dismissed_version).toBe("9.9.9");
    expect(shouldShowUpdateDialog(prefs, "9.9.9")).toBe(false);
    expect(shouldShowUpdateDialog(prefs, "9.9.10")).toBe(true);
  });

  it("稍后再说 does not start download", async () => {
    __setUpdaterSnapshotForTests({
      phase: "available",
      currentVersion: "1.0.2",
      latestVersion: "1.0.3",
      releaseNotes: "notes",
      message: "发现新版本 1.0.3",
    });
    const downloadSpy = vi.fn();
    const snap = dismissAvailableUpdate();
    expect(snap.phase).toBe("dismissed");
    expect(downloadSpy).not.toHaveBeenCalled();
    expect(loadUpdaterPreferences().dismissed_version).toBe("1.0.3");
    expect(getUpdaterSnapshot().latestVersion).toBe("1.0.3");
  });

  it("startDownload without pending update fails safely (no install)", async () => {
    __setUpdaterSnapshotForTests({
      phase: "available",
      currentVersion: "1.0.2",
      latestVersion: "1.0.3",
    });
    const snap = await startDownload();
    expect(snap.phase).toBe("failed");
    expect(snap.phase).not.toBe("installing");
    expect(snap.phase).not.toBe("restart_required");
  });

  it("confirmInstall requires downloaded phase", async () => {
    __setUpdaterSnapshotForTests({
      phase: "available",
      currentVersion: "1.0.2",
      latestVersion: "1.0.3",
    });
    const snap = await confirmInstall();
    expect(snap.phase).toBe("failed");
    expect(snap.message).toMatch(/先完成下载/);
  });

  it("deferInstall keeps downloaded package without relaunch", () => {
    __setUpdaterSnapshotForTests({
      phase: "downloaded",
      currentVersion: "1.0.2",
      latestVersion: "1.0.3",
      message: "ready",
    });
    const snap = deferInstall();
    expect(snap.phase).toBe("downloaded");
    expect(snap.message).toMatch(/稍后/);
  });

  it("browser check does not download or install", async () => {
    const result = await checkForAppUpdate(true);
    expect(result.kind).toBe("disabled");
    const snap = getUpdaterSnapshot();
    expect(snap.phase).not.toBe("downloading");
    expect(snap.phase).not.toBe("installing");
  });

  it("ui audit manual check shows dialog data without download", async () => {
    sessionStorage.setItem("storylens.uiAudit", "1");
    const result = await checkForAppUpdate(true);
    expect(result.kind).toBe("available");
    if (result.kind !== "available") return;
    await expect(result.downloadAndInstall()).rejects.toThrow(/禁止自动下载安装|已禁用/);
    expect(getUpdaterSnapshot().phase).toBe("available");
  });

  it("audit download reaches downloaded without auto install", async () => {
    sessionStorage.setItem("storylens.uiAudit", "1");
    await checkForAppUpdate(true);
    const afterDownload = await startDownload();
    expect(afterDownload.phase).toBe("downloaded");
    expect(afterDownload.phase).not.toBe("installing");
    expect(afterDownload.phase).not.toBe("restart_required");
  });

  it("user confirm install moves to restart_required without deleting data markers", async () => {
    sessionStorage.setItem("storylens.uiAudit", "1");
    await checkForAppUpdate(true);
    await startDownload();
    localStorage.setItem("storylens.user-data-marker", "keep-me");
    const afterInstall = await confirmInstall();
    expect(afterInstall.phase).toBe("restart_required");
    expect(localStorage.getItem("storylens.user-data-marker")).toBe("keep-me");
  });
});
