import { setApiBase, refreshApiBaseFromTauri } from "./apiClient";

export type BackendUiStatus =
  | { state: "browser_dev" }
  | { state: "starting" }
  | { state: "ready"; apiBase: string }
  | { state: "failed"; message: string };

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function invoke<T>(cmd: string): Promise<T> {
  const { invoke: tauriInvoke } = await import("@tauri-apps/api/core");
  return tauriInvoke<T>(cmd);
}

async function waitForHealth(apiBase: string, timeoutMs = 60_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${apiBase}/health`);
      if (response.ok) return;
    } catch {
      // keep polling
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error("本地分析服务启动超时。请确认没有其他程序占用端口后重试。");
}

export async function bootstrapDesktopRuntime(
  onStatus?: (status: BackendUiStatus) => void,
): Promise<BackendUiStatus> {
  if (!isTauriRuntime()) {
    // Production SPA served by FastAPI uses same-origin relative API paths.
    // Explicit build-time VITE_API_BASE_URL (acceptance vite preview) must be preserved.
    if (!import.meta.env.DEV) {
      const baked =
        typeof import.meta.env.VITE_API_BASE_URL === "string"
          ? import.meta.env.VITE_API_BASE_URL.trim()
          : "";
      if (!baked) {
        setApiBase("");
      }
    }
    // Browser / Vitest: API is started separately (start-dev.ps1 / start_storylens_web.ps1).
    onStatus?.({ state: "browser_dev" });
    return { state: "browser_dev" };
  }

  onStatus?.({ state: "starting" });
  const deadline = Date.now() + 90_000;
  let lastError = "本地分析服务正在启动…";

  while (Date.now() < deadline) {
    try {
      const status = await invoke<{
        state: string;
        api_base?: string;
        user_message?: string;
      }>("get_backend_status");

      if (status.state === "ready" && status.api_base) {
        setApiBase(status.api_base);
        await waitForHealth(status.api_base, 15_000);
        const ready = { state: "ready" as const, apiBase: status.api_base };
        onStatus?.(ready);
        return ready;
      }
      if (status.state === "failed") {
        const message = status.user_message || "本地分析服务启动失败。";
        const failed = { state: "failed" as const, message };
        onStatus?.(failed);
        return failed;
      }
      lastError = "本地分析服务正在启动，请稍候…";
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((r) => setTimeout(r, 400));
  }

  const failed = {
    state: "failed" as const,
    message: lastError || "本地分析服务启动失败。请重启 StoryLens。",
  };
  onStatus?.(failed);
  return failed;
}

export async function listenBackendEvents(
  onError: (message: string) => void,
  onReady?: (apiBase: string) => void,
): Promise<() => void> {
  if (!isTauriRuntime()) return () => undefined;
  const { listen } = await import("@tauri-apps/api/event");
  const unlistenError = await listen<string>("backend-error", (event) => {
    onError(event.payload || "本地分析服务异常退出。");
  });
  const unlistenReady = await listen<string>("backend-ready", async (event) => {
    const payload = typeof event.payload === "string" ? event.payload.trim() : "";
    if (payload) {
      setApiBase(payload);
      onReady?.(payload);
      return;
    }
    const refreshed = await refreshApiBaseFromTauri();
    if (refreshed) onReady?.(refreshed);
  });
  return () => {
    unlistenError();
    unlistenReady();
  };
}

export { isTauriRuntime };
