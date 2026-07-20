import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../services/apiClient";
import { useUiStore } from "../../stores/uiStore";
import { DevelopmentNavigationGroup } from "./DevelopmentNavigationGroup";

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
  const { theme, setTheme } = useUiStore();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<Record<string, string>>("/health"),
    refetchInterval: 15000,
  });
  const service = serviceLabel(health);
  const nextTheme = theme === "light" ? "dark" : "light";
  const themeLabel = nextTheme === "dark" ? "切换到深色模式" : "切换到浅色模式";
  const techTitle = [
    health.isSuccess ? "后端：已连接" : health.isLoading || health.isFetching ? "后端：连接中" : "后端：离线",
    health.data?.database ? `DB ${health.data.database}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="app app-shell-simplified" data-theme={theme} data-testid="app-shell">
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
          <span className="brand-text">
            <b>StoryLens</b>
            <small className="brand-tagline">小说拆解工作台</small>
          </span>
        </button>
        <div className="top-status">
          <button
            type="button"
            className="theme-toggle-btn"
            onClick={() => setTheme(nextTheme)}
            aria-label={themeLabel}
            title={themeLabel}
            aria-pressed={theme === "dark"}
            data-theme-current={theme}
          >
            <span className="theme-toggle-icon" aria-hidden="true">
              {theme === "light" ? "◐" : "◑"}
            </span>
          </button>
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
          <p className="nav-version" data-testid="app-footer">
            StoryLens 1.0.0-rc1
          </p>
        </div>
      </aside>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
