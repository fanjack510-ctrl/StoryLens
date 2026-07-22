import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "./AppShell";
import { HomePage } from "../../pages/HomePage";
import { LibraryPage } from "../../pages/LibraryPage";
import { useOnboardingStore } from "../../stores/onboardingStore";
import { useUiStore } from "../../stores/uiStore";

vi.stubGlobal(
  "fetch",
  vi.fn(async (url: string) => {
    const href = String(url);
    if (href.includes("/health")) {
      return new Response(
        JSON.stringify({ status: "ok", database: "ok", default_provider: "none" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (href.includes("/books")) {
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (href.includes("/model-providers") || href.includes("/providers")) {
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (href.includes("/analysis-runs")) {
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (href.includes("dashboard") || href.includes("diagnostics") || href.includes("cloud")) {
      return new Response(
        JSON.stringify({
          books: 0,
          chapters: 0,
          paragraphs: 0,
          scenes: 0,
          successful_runs: 0,
          failed_runs: 0,
          enabled: false,
          cloud_request_budget_enabled: true,
          cloud_max_input_tokens_per_request: 1,
          cloud_max_output_tokens_per_request: 1,
          cloud_max_requests_per_run: 1,
          cloud_daily_request_limit: 1,
          cloud_daily_token_limit: 1,
          cloud_daily_estimated_cost_limit: 1,
          cloud_stop_on_unknown_pricing: true,
          cloud_confirm_each_paid_test: true,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
);

function renderShell(initial = "/library") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/settings" element={<div>设置页</div>} />
            <Route path="/tasks" element={<div data-testid="tasks-route">任务中心</div>} />
            <Route path="/workspace" element={<div>工作台</div>} />
            <Route path="/cases" element={<div>案例库</div>} />
            <Route path="/providers" element={<div>模型</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("UI shell navigation", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    localStorage.removeItem("storylens.nav.devExpanded");
    localStorage.removeItem("storylens.developerMode");
    localStorage.removeItem("storylens.onboarding.v1");
    useOnboardingStore.setState({ status: "completed" });
    useUiStore.setState({ theme: "light" });
  });

  it("shows only library and settings in primary nav", () => {
    renderShell("/library");
    expect(screen.getByText("小说叙事洞察与创作平台")).toBeInTheDocument();
    const nav = screen.getByTestId("primary-nav");
    expect(within(nav).getByTestId("nav-library")).toBeInTheDocument();
    expect(within(nav).getByTestId("nav-settings")).toBeInTheDocument();
    expect(within(nav).queryByText("任务中心")).not.toBeInTheDocument();
    expect(within(nav).queryByText("案例库")).not.toBeInTheDocument();
    expect(within(nav).queryByText("首页")).not.toBeInTheDocument();
    expect(within(nav).queryByText("系统状态")).not.toBeInTheDocument();
    expect(within(nav).queryByText("模型与API")).not.toBeInTheDocument();
    expect(within(nav).queryByText("模型与 API")).not.toBeInTheDocument();
    expect(within(nav).queryByText("开发工具")).not.toBeInTheDocument();
  });

  it("enables developer mode and keeps old routes reachable", () => {
    renderShell("/library");
    expect(screen.queryByTestId("dev-nav-panel")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("开发者模式"));
    expect(screen.getByTestId("dev-nav-panel")).toBeInTheDocument();
    expect(within(screen.getByTestId("dev-nav-panel")).getByText("开发工具")).toBeInTheDocument();
    expect(within(screen.getByTestId("dev-nav-panel")).queryByText("系统状态")).not.toBeInTheDocument();
    fireEvent.click(within(screen.getByTestId("dev-nav-panel")).getByText("任务中心"));
    expect(screen.getByTestId("tasks-route")).toBeInTheDocument();
  });

  it("theme button toggles real theme state", () => {
    renderShell("/library");
    expect(screen.getByTestId("app-shell")).toHaveAttribute("data-theme", "light");
    fireEvent.click(screen.getByLabelText("切换到深色模式"));
    expect(useUiStore.getState().theme).toBe("dark");
    expect(screen.getByTestId("app-shell")).toHaveAttribute("data-theme", "dark");
    fireEvent.click(screen.getByLabelText("切换到浅色模式"));
    expect(useUiStore.getState().theme).toBe("light");
  });

  it("shows friendly local service status instead of raw DB text", async () => {
    renderShell("/library");
    await waitFor(() => {
      expect(screen.getByTestId("nav-service-status")).toHaveTextContent("本地服务正常");
    });
    const status = screen.getByTestId("nav-service-status");
    expect(status).not.toHaveTextContent("DB ok");
    expect(status.getAttribute("title") || "").toContain("DB");
  });

  it("shows build-injected app version in footer without stale hardcodes", async () => {
    renderShell("/library");
    const footer = await screen.findByTestId("app-footer");
    await waitFor(() => {
      expect(footer.textContent || "").toMatch(/StoryLens\s*·\s*\d+\.\d+\.\d+/);
    });
    expect(footer).not.toHaveTextContent("1.0.0-rc1");
    expect(footer).not.toHaveTextContent("0.1.0");
    expect(footer).not.toHaveTextContent("版本未知");
  });

  it("redirects home to library", async () => {
    renderShell("/");
    expect(await screen.findByTestId("library-page")).toBeInTheDocument();
  });
});
