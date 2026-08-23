import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAppVersion } from "../../lib/useAppVersion";
import { useProductEdition } from "../../hooks/useProductEdition";
import { api, onApiBaseChange } from "../../services/apiClient";
import {
  formatRuntimeFingerprint,
  getRuntimeFingerprint,
} from "../../services/runtimeFingerprint";
import { isLocalWebShell, useRuntimeInfo } from "../../services/runtimeCapabilities";
import { useUiStore } from "../../stores/uiStore";
import { DocumentTitleSync } from "../product/DocumentTitleSync";
import { ProductEditionBadge } from "../product/ProductEditionBadge";
import { AppearanceThemeMenu } from "./AppearanceThemeMenu";

const PRIMARY_NAV: Array<[string, string, string]> = [
  ["/library", "我的书库", "▤"],
  // 跨书检索的范围是整个书库，不属于任何一本书——所以它在应用级导航里，
  // 而不是某本书的页面上。
  ["/search", "检索", "⌕"],
  ["/settings", "设置", "◉"],
];

function serviceLabel(health: {
  isLoading: boolean;
  isFetching: boolean;
  isSuccess: boolean;
  isError: boolean;
  failureCount: number;
}): { text: string; tone: "ok" | "off" | "pending" } {
  // Prefer live error over a stale prior success (Sidecar bounce / port change).
  if (health.isError && health.failureCount > 0 && !health.isFetching) {
    return { text: "本地服务离线", tone: "off" };
  }
  if (health.isSuccess && !health.isError) return { text: "本地服务正常", tone: "ok" };
  if (health.isLoading || health.isFetching) return { text: "正在连接", tone: "pending" };
  return { text: "本地服务离线", tone: "off" };
}

export function AppShell() {
  const navigate = useNavigate();
  const appVersion = useAppVersion();
  const edition = useProductEdition();
  const theme = useUiStore((s) => s.theme);
  const runtime = useRuntimeInfo();
  const webShell = isLocalWebShell(runtime.data);
  const [buildFingerprint, setBuildFingerprint] = useState(() => {
    const fp = getRuntimeFingerprint();
    if (import.meta.env.DEV) return formatRuntimeFingerprint(fp);
    // Acceptance / preview builds bake VITE_PUBLIC_GIT_HEAD — surface Commit SHA on page.
    if (fp.publicHead && fp.publicHead !== "unknown") {
      return `Build ${fp.publicHead} · API ${fp.apiPort || fp.apiBase}`;
    }
    return "";
  });
  useEffect(() => {
    const refresh = () => {
      const fp = getRuntimeFingerprint();
      if (import.meta.env.DEV) {
        setBuildFingerprint(formatRuntimeFingerprint(fp));
        return;
      }
      if (fp.publicHead && fp.publicHead !== "unknown") {
        setBuildFingerprint(`Build ${fp.publicHead} · API ${fp.apiPort || fp.apiBase}`);
      }
    };
    refresh();
    return onApiBaseChange(() => refresh());
  }, []);
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<Record<string, string>>("/health"),
    refetchInterval: 15000,
  });
  const service = serviceLabel(health);
  const techTitle = [
    health.isSuccess ? "后端：已连接" : health.isLoading || health.isFetching ? "后端：连接中" : "后端：离线",
    health.data?.database ? `DB ${health.data.database}` : null,
    runtime.data?.runtime_mode ? `mode ${runtime.data.runtime_mode}` : null,
    import.meta.env.DEV ? `fp ${getRuntimeFingerprint().publicHead}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div
      className="app app-shell-simplified"
      data-theme={theme}
      data-testid="app-shell"
      data-runtime-mode={runtime.data?.runtime_mode || "unknown"}
      data-shell={webShell ? "local-web" : "desktop"}
      data-product-edition={edition.loaded ? edition.edition : "pending"}
    >
      <DocumentTitleSync />
      <header className="app-topbar">
        <button
          type="button"
          className="brand brand-with-mark"
          onClick={() => navigate("/library")}
          aria-label="StoryLens 首页"
        >
          <span className="brand-mark" aria-hidden="true">
            SL
          </span>
          <span className="brand-text brand-text-row">
            <b data-testid="app-brand-label" className="brand-label-row">
              <span data-testid="app-brand-name">StoryLens</span>
              <ProductEditionBadge edition={edition} />
              {webShell ? (
                <span className="brand-shell-sep" data-testid="app-shell-label">
                  {" "}
                  · 本地网页版
                </span>
              ) : null}
            </b>
          </span>
        </button>
        {/* 导航进顶栏。它原来是左边一条 200px 的常驻竖栏，只装着两个入口——而打开一本书之后
            它还在，于是屏幕上同时有两条竖栏：一条问「你要去哪个页面」，一条问「你要读哪一章」。
            450 像素用来放导航，而那一整屏本来是用来读小说的。 */}
        <nav className="primary-nav-links" data-testid="primary-nav">
          {PRIMARY_NAV.map(([to, label, icon]) => (
            <NavLink key={to} to={to} data-testid={`nav-${to.slice(1)}`}>
              <i>{icon}</i>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="top-status">
          {/* 「本地服务正常」是一个圆点加四个字的事，不必占一整块页脚。
              版本号和构建指纹收进设置页——那是排查问题时才找的东西，不是每天要看的。 */}
          <p
            className={`nav-service-status nav-service-status--${service.tone}`}
            data-testid="nav-service-status"
            title={techTitle}
          >
            <span className="nav-service-dot" aria-hidden="true" />
            {service.text}
          </p>
          {edition.loaded ? (
            <button
              type="button"
              className={`nav-edition-identity ${edition.is_pro ? "nav-edition-identity--pro" : ""}`}
              data-testid="nav-edition-identity"
              data-edition={edition.edition}
              onClick={() => navigate("/settings?tab=license")}
              title="打开授权与专业版"
            >
              {edition.product_line_name}
            </button>
          ) : (
            <p className="nav-edition-identity nav-edition-identity--pending" data-testid="nav-edition-identity">
              …
            </p>
          )}
          <AppearanceThemeMenu />
        </div>
        {/* 版本号与构建指纹留在 DOM 里但不显示：验收脚本和问题排查都按这两个 testid 找它们，
            拿掉会让「用户看不到」变成「谁都读不到」。 */}
        <span hidden data-testid="app-footer">
          {webShell ? "本地网页版" : "StoryLens"} · {appVersion}
        </span>
        {buildFingerprint ? (
          <span
            hidden
            data-testid="runtime-dev-fingerprint"
            data-build-fingerprint="1"
            title={getRuntimeFingerprint().apiBase}
          >
            {buildFingerprint}
          </span>
        ) : null}
        {edition.user_error_message ? (
          <span hidden data-testid="nav-edition-error">
            {edition.user_error_message}
          </span>
        ) : null}
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
