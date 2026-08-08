import { useEffect, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useDeveloperModeStore } from "../../stores/developerModeStore";

const DEV_LINKS: Array<[string, string]> = [
  ["/workspace", "分析工作台"],
  ["/tasks", "任务中心"],
  ["/cases", "案例库"],
  ["/providers", "AI 诊断"],
];

type Props = {
  children?: ReactNode;
};

/**
 * Bottom nav: developer mode switch (default off).
 * When off, engineering routes and health dump stay hidden.
 */
export function DevelopmentNavigationGroup({ children }: Props) {
  const developerMode = useDeveloperModeStore((s) => s.developerMode);
  const setDeveloperMode = useDeveloperModeStore((s) => s.setDeveloperMode);

  useEffect(() => {
    // Keep legacy key in sync for any residual readers.
    try {
      localStorage.setItem("storylens.nav.devExpanded", developerMode ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [developerMode]);

  return (
    <div className="dev-nav-group" data-testid="dev-nav-group">
      <label className="dev-mode-toggle" data-testid="dev-nav-toggle">
        <span>
          <i>▦</i>
          开发者模式
        </span>
        <input
          type="checkbox"
          role="switch"
          className="settings-switch"
          checked={developerMode}
          aria-label="开发者模式"
          aria-expanded={developerMode}
          onChange={(e) => setDeveloperMode(e.target.checked)}
        />
      </label>
      {developerMode && (
        <div className="dev-nav-panel" data-testid="dev-nav-panel">
          <p className="dev-nav-group-title">开发工具</p>
          <nav className="dev-nav-links">
            {DEV_LINKS.map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                data-testid={`dev-nav-link-${to.replace(/\//g, "") || "root"}`}
              >
                {label}
              </NavLink>
            ))}
          </nav>
          {children}
        </div>
      )}
    </div>
  );
}
