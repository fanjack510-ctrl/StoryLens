/// <reference types="vite/client" />

/** Injected by vite.config from package.json (synced from root VERSION via version_manager.py). */
declare const __STORYLENS_APP_VERSION__: string;

/** Injected by vite.config from `git rev-parse HEAD` (DEV fingerprint). */
declare const __STORYLENS_PUBLIC_GIT_HEAD__: string;

/** Injected by vite.config from VITE_PRO_NATIVE_OVERVIEW_ENABLED (RC builds may enable). */
declare const __STORYLENS_PRO_NATIVE_OVERVIEW_ENABLED__: boolean;

/** Injected by vite.config from VITE_WHOLE_BOOK_DIAGNOSTICS_ENABLED (Wave B dev page). */
declare const __STORYLENS_WHOLE_BOOK_DIAGNOSTICS_ENABLED__: boolean;

/** Injected by vite.config from VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED (Wave D formal page). */
declare const __STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED__: boolean;

/** Injected by vite.config from VITE_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED (Wave D fixture preview). */
declare const __STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED__: boolean;

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_TELEMETRY_ENDPOINT?: string;
  readonly VITE_TELEMETRY_PROJECT_KEY?: string;
  readonly VITE_PRO_NATIVE_OVERVIEW_ENABLED?: string;
  readonly VITE_WHOLE_BOOK_DIAGNOSTICS_ENABLED?: string;
  readonly VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED?: string;
  readonly VITE_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED?: string;
  readonly VITE_PUBLIC_GIT_HEAD?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
