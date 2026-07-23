import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "./AppShell";
import { SettingsAppearanceTab } from "../settings/SettingsAppearanceTab";
import { useUiStore } from "../../stores/uiStore";
import { APPEARANCE_THEME_STORAGE_KEY } from "../../lib/appearanceTheme";
import { useOnboardingStore } from "../../stores/onboardingStore";

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
            <Route path="/library" element={<div data-testid="library-route">书库</div>} />
            <Route path="/settings" element={<SettingsAppearanceTab />} />
            <Route path="/books/:id" element={<div data-testid="book-route">正文</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Appearance theme header control", () => {
  beforeEach(() => {
    localStorage.clear();
    useOnboardingStore.setState({ status: "completed" });
    useUiStore.setState({ theme: "light" });
    document.documentElement.dataset.theme = "light";
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("shows labeled control on the top-right and persists dark choice", () => {
    renderShell("/library");
    const trigger = screen.getByTestId("appearance-theme-trigger");
    expect(trigger).toHaveTextContent("浅色");
    expect(screen.getByTestId("app-shell")).toHaveAttribute("data-theme", "light");

    fireEvent.click(trigger);
    fireEvent.click(screen.getByTestId("appearance-theme-option-dark"));

    expect(useUiStore.getState().theme).toBe("dark");
    expect(localStorage.getItem(APPEARANCE_THEME_STORAGE_KEY)).toBe("dark");
    expect(screen.getByTestId("app-shell")).toHaveAttribute("data-theme", "dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByTestId("appearance-theme-trigger")).toHaveTextContent("深色");
  });

  it("keeps theme across routes and settings has no editable theme select", () => {
    renderShell("/library");
    fireEvent.click(screen.getByTestId("appearance-theme-trigger"));
    fireEvent.click(screen.getByTestId("appearance-theme-option-dark"));

    fireEvent.click(screen.getByTestId("nav-settings"));
    expect(screen.getByTestId("settings-panel-appearance")).toBeInTheDocument();
    expect(screen.getByTestId("appearance-theme-relocated-hint")).toHaveTextContent("右上角");
    expect(screen.queryByLabelText("主题")).not.toBeInTheDocument();
    expect(screen.getByTestId("app-shell")).toHaveAttribute("data-theme", "dark");
    expect(within(document.body).getByTestId("appearance-theme-trigger")).toHaveTextContent(
      "深色",
    );
  });

  it("closes menu on Escape", () => {
    renderShell("/library");
    fireEvent.click(screen.getByTestId("appearance-theme-trigger"));
    expect(screen.getByTestId("appearance-theme-panel")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("appearance-theme-panel")).not.toBeInTheDocument();
  });
});
