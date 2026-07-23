import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAppVersion } from "../../lib/useAppVersion";
import { useProductEdition } from "../../hooks/useProductEdition";
import { api } from "../../services/apiClient";
import { isLocalWebShell, useRuntimeInfo } from "../../services/runtimeCapabilities";
import { useUiStore } from "../../stores/uiStore";
import { DocumentTitleSync } from "../product/DocumentTitleSync";
import { ProductEditionBadge } from "../product/ProductEditionBadge";
import { DevelopmentNavigationGroup } from "./DevelopmentNavigationGroup";
import { AppearanceThemeMenu } from "./AppearanceThemeMenu";

const PRIMARY_NAV: Array<[string, string, string]> = [
  ["/library", "我的书库", "▤"],
  ["/settings", "设置", "◉"],
];

function serviceLabel(health: {
  isLoading: boolean;
  isFetching: boolean;
  isSuccess: boolean;
  isError: boolean;
}): { text: string; tone: "ok" | "off" | "pending" } {
  if (health.isSuccess) return { text: "本地服务正常", tone: "ok" };
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
        <div className="context">小说叙事洞察与创作平台</div>
        <div className="top-status">
          <AppearanceThemeMenu />
        </div>
      </header>
      <aside className="app-nav" data-testid="primary-nav">
        <nav className="primary-nav-links">
          {PRIMARY_NAV.map(([to, label, icon]) => (
            <NavLink key={to} to={to} data-testid={`nav-${to.slice(1)}`}>
              <i>{icon}</i>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="nav-spacer" />
        <div className="nav-footer-block">
          <p
            className={`nav-service-status nav-service-status--${service.tone}`}
            data-testid="nav-service-status"
            title={techTitle}
          >
            <span className="nav-service-dot" aria-hidden="true" />
            {service.text}
          </p>
          <DevelopmentNavigationGroup />
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
          {edition.user_error_message ? (
            <p className="nav-edition-note" data-testid="nav-edition-error">
              {edition.user_error_message}
            </p>
          ) : null}
          <p className="nav-version" data-testid="app-footer">
            {webShell ? "本地网页版" : "StoryLens"} · {appVersion}
          </p>
        </div>
      </aside>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
