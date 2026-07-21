/// <reference types="vite/client" />

/** Injected by vite.config from package.json (synced from root VERSION via version_manager.py). */
declare const __STORYLENS_APP_VERSION__: string;

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_TELEMETRY_ENDPOINT?: string;
  readonly VITE_TELEMETRY_PROJECT_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
