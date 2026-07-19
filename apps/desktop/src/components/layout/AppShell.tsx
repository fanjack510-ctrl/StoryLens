import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../services/apiClient";
import { useUiStore } from "../../stores/uiStore";
import { DevelopmentNavigationGroup } from "./DevelopmentNavigationGroup";

const PRIMARY_NAV: Array<[string, string, string]> = [
  ["/library", "我的书库", "▤"],
  ["/settings", "设置", "◉"],
];

export function AppShell() {
  const navigate = useNavigate();
  const { theme, setTheme } = useUiStore();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<Record<string, string>>("/health"),
    refetchInterval: 15000,
  });

  return (
    <div className="app app-shell-simplified" data-theme={theme} data-testid="app-shell">
      <header className="app-topbar">
        <button type="button" className="brand" onClick={() => navigate("/library")}>
          SL <b>StoryLens</b>
        </button>
        <div className="context">小说拆解工作台</div>
        <div className="top-status">
          <button
            type="button"
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            aria-label="切换主题"
          >
            {theme === "light" ? "深色" : "亮色"}
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
        <DevelopmentNavigationGroup>
          <p className="dev-nav-health" data-testid="dev-health-summary">
            后端：{health.isSuccess ? "已连接" : "离线"}
            {health.data?.database ? ` · DB ${health.data.database}` : ""}
          </p>
        </DevelopmentNavigationGroup>
      </aside>
      <main>
        <Outlet />
      </main>
      <footer className="app-footer-minimal" data-testid="app-footer">
        <span>StoryLens 1.0.0-rc1</span>
      </footer>
    </div>
  );
}
