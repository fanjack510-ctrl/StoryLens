import {
  normalizeUpdateChannel,
  type UpdateChannel,
} from "./channels";

const STORAGE_KEY = "storylens.updater.preferences.v1";

export type UpdaterPreferences = {
  /** Default true — startup / scheduled check only. */
  automatic_check: boolean;
  /** Default false — never download without explicit user action. */
  automatic_download: boolean;
  /** Default false — never install without explicit user action. */
  automatic_install: boolean;
  channel: UpdateChannel;
  dismissed_version: string | null;
  /** ISO timestamp; dialog may stay quiet until then, settings still show update. */
  remind_after: string | null;
  last_check_at: string | null;
  /** Internal test mode unlocks staging channel selection. */
  internal_test_mode: boolean;
};

export const DEFAULT_UPDATER_PREFERENCES: UpdaterPreferences = {
  automatic_check: true,
  automatic_download: false,
  automatic_install: false,
  channel: "stable",
  dismissed_version: null,
  remind_after: null,
  last_check_at: null,
  internal_test_mode: false,
};

function canUseStorage(): boolean {
  return typeof localStorage !== "undefined";
}

export function loadUpdaterPreferences(): UpdaterPreferences {
  if (!canUseStorage()) {
    return { ...DEFAULT_UPDATER_PREFERENCES };
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_UPDATER_PREFERENCES };
    const parsed = JSON.parse(raw) as Partial<UpdaterPreferences>;
    return {
      automatic_check: parsed.automatic_check !== false,
      // Hard policy: never default these on, even if a stale value said true.
      automatic_download: false,
      automatic_install: false,
      channel: normalizeUpdateChannel(parsed.channel),
      dismissed_version:
        typeof parsed.dismissed_version === "string" ? parsed.dismissed_version : null,
      remind_after: typeof parsed.remind_after === "string" ? parsed.remind_after : null,
      last_check_at: typeof parsed.last_check_at === "string" ? parsed.last_check_at : null,
      internal_test_mode: parsed.internal_test_mode === true,
    };
  } catch {
    return { ...DEFAULT_UPDATER_PREFERENCES };
  }
}

export function saveUpdaterPreferences(prefs: UpdaterPreferences): void {
  if (!canUseStorage()) return;
  try {
    const safe: UpdaterPreferences = {
      ...prefs,
      // Persist policy defaults — remote manifests must not flip these on.
      automatic_download: false,
      automatic_install: false,
      channel: prefs.internal_test_mode ? normalizeUpdateChannel(prefs.channel) : "stable",
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(safe));
  } catch {
    /* ignore quota / private mode */
  }
}

export function patchUpdaterPreferences(
  patch: Partial<UpdaterPreferences>,
): UpdaterPreferences {
  const next = { ...loadUpdaterPreferences(), ...patch };
  // Enforce non-negotiable defaults for this release track.
  next.automatic_download = false;
  next.automatic_install = false;
  if (!next.internal_test_mode) {
    next.channel = "stable";
  }
  saveUpdaterPreferences(next);
  return next;
}

/** Dialog may be suppressed temporarily; settings must still show the update. */
export function shouldShowUpdateDialog(
  prefs: UpdaterPreferences,
  latestVersion: string,
): boolean {
  if (!prefs.dismissed_version || prefs.dismissed_version !== latestVersion) {
    return true;
  }
  if (!prefs.remind_after) {
    return false;
  }
  const remindAt = Date.parse(prefs.remind_after);
  if (Number.isNaN(remindAt)) {
    return false;
  }
  return Date.now() >= remindAt;
}

export function markUpdateDismissed(latestVersion: string, remindHours = 24): UpdaterPreferences {
  const remindAfter = new Date(Date.now() + remindHours * 60 * 60 * 1000).toISOString();
  return patchUpdaterPreferences({
    dismissed_version: latestVersion,
    remind_after: remindAfter,
  });
}
