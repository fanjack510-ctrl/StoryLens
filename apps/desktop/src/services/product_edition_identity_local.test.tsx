import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "../components/layout/AppShell";
import { LicenseSettingsCard } from "../components/settings/LicenseSettingsCard";
import type { EntitlementSnapshot } from "./entitlementApi";
import {
  buildProductEditionState,
  documentTitleForEdition,
} from "./productEdition";

function freeSnap(): EntitlementSnapshot {
  return {
    edition: "free",
    edition_label: "StoryLens 免费版",
    license_id: null,
    license_id_masked: null,
    major_version: null,
    activated_at: null,
    features: {
      whole_book_analysis: false,
      narrative_asset_library: false,
      story_lab: false,
      cross_book_search: false,
      advanced_export: false,
    },
    pro_active: false,
    commerce: {
      afdian_product_url: "https://afdian.com/item/demo",
      product_code: "storylens_pro",
      product_label: "StoryLens Pro",
    },
  };
}

function proSnap(): EntitlementSnapshot {
  return {
    ...freeSnap(),
    edition: "pro",
    edition_label: "StoryLens Pro",
    pro_active: true,
    license_id: "3c1fd624-aaaa-bbbb-cccc-dddddddd40b3",
    license_id_masked: "3c1fd624…40b3",
    major_version: 1,
    activated_at: "2026-07-22T04:26:00+00:00",
  };
}

let snapshot: EntitlementSnapshot = freeSnap();
let entitlementMode: "ok" | "error" = "ok";

vi.mock("./runtimeCapabilities", async () => {
  const actual = await vi.importActual<typeof import("./runtimeCapabilities")>("./runtimeCapabilities");
  return {
    ...actual,
    useRuntimeInfo: () => ({
      data: {
        runtime_mode: "browser_local_production",
        shell: "browser_local_production",
        user_label: "本地网页版",
      },
      isLoading: false,
      isError: false,
    }),
    isLocalWebShell: () => true,
  };
});

vi.mock("../lib/useAppVersion", () => ({
  useAppVersion: () => "1.0.3",
}));

vi.stubGlobal(
  "fetch",
  vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const href = String(input);
    if (href.includes("/health")) {
      return new Response(JSON.stringify({ status: "ok", database: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (href.includes("/api/v1/licenses/activate") && init?.method === "POST") {
      snapshot = proSnap();
      return new Response(
        JSON.stringify({
          ok: true,
          user_message: "StoryLens Pro 已激活",
          entitlement: snapshot,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (href.includes("/api/v1/entitlements")) {
      if (entitlementMode === "error") {
        return new Response(JSON.stringify({ detail: "offline" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(snapshot), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
  }),
);

function wrapShell(path = "/library") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/library" element={<div>书库</div>} />
            <Route path="/settings" element={<LicenseSettingsCard />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("productEdition helpers", () => {
  it("builds free and pro identity without VIP wording", () => {
    const free = buildProductEditionState({
      snapshot: freeSnap(),
      loaded: true,
      applicationVersion: "1.0.3",
    });
    expect(free.edition).toBe("free");
    expect(free.product_line_name).toBe("StoryLens 免费版");
    expect(free.is_pro).toBe(false);
    const pro = buildProductEditionState({
      snapshot: proSnap(),
      loaded: true,
      applicationVersion: "1.0.3",
    });
    expect(pro.edition).toBe("pro");
    expect(pro.product_line_name).toBe("StoryLens Pro");
    expect(JSON.stringify(pro)).not.toMatch(/VIP|会员/);
  });

  it("degrades safely on error without assuming pro", () => {
    const state = buildProductEditionState({
      loaded: true,
      error: new Error("offline"),
      applicationVersion: "1.0.3",
    });
    expect(state.is_pro).toBe(false);
    expect(state.user_error_message).toBe("暂时无法读取专业版授权状态。");
  });

  it("document titles follow free/pro rules", () => {
    expect(documentTitleForEdition("free")).toBe("StoryLens");
    expect(documentTitleForEdition("pro")).toBe("StoryLens Pro");
    expect(documentTitleForEdition("pro", "我的书库")).toBe("我的书库 · StoryLens Pro");
    expect(documentTitleForEdition("free", "设置")).toBe("设置 · StoryLens");
  });
});

describe("AppShell product edition identity", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    snapshot = freeSnap();
    entitlementMode = "ok";
    document.title = "StoryLens";
    vi.mocked(fetch).mockClear();
  });

  it("shows free badge and sidebar identity", async () => {
    wrapShell();
    await waitFor(() => {
      expect(screen.getByTestId("app-edition-badge")).toHaveTextContent("免费版");
    });
    expect(screen.getByTestId("app-brand-name")).toHaveTextContent("StoryLens");
    expect(screen.getByTestId("app-shell-label")).toHaveTextContent("本地网页版");
    expect(screen.getByTestId("nav-edition-identity")).toHaveTextContent("StoryLens 免费版");
    expect(screen.getByTestId("app-footer")).toHaveTextContent("本地网页版 · 1.0.3");
    await waitFor(() => {
      expect(document.title).toMatch(/StoryLens/);
    });
    expect(document.title).not.toMatch(/Pro/);
    expect(document.body.textContent).not.toMatch(/VIP/);
  });

  it("shows Pro badge and sidebar identity", async () => {
    snapshot = proSnap();
    wrapShell();
    await waitFor(() => {
      expect(screen.getByTestId("app-edition-badge")).toHaveTextContent("Pro");
    });
    expect(screen.getByTestId("nav-edition-identity")).toHaveTextContent("StoryLens Pro");
    await waitFor(() => {
      expect(document.title).toMatch(/StoryLens Pro/);
    });
    expect(screen.queryByText(proSnap().license_id!)).not.toBeInTheDocument();
  });

  it("navigates to license settings from sidebar identity", async () => {
    wrapShell();
    await waitFor(() => {
      expect(screen.getByTestId("nav-edition-identity")).toHaveTextContent("StoryLens");
    });
    fireEvent.click(screen.getByTestId("nav-edition-identity"));
    await waitFor(() => {
      expect(screen.getByTestId("settings-panel-license")).toBeInTheDocument();
    });
  });

  it("updates shell immediately after activate without reload", async () => {
    wrapShell("/settings");
    await waitFor(() => {
      expect(screen.getByTestId("app-edition-badge")).toHaveTextContent("免费版");
    });
    await waitFor(() => screen.getByTestId("license-open-activate"));
    fireEvent.click(screen.getByTestId("license-open-activate"));
    fireEvent.change(screen.getByTestId("license-code-input"), {
      target: { value: "SLP1-demo.sig" },
    });
    fireEvent.click(screen.getByTestId("license-activate-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("app-edition-badge")).toHaveTextContent("Pro");
    });
    expect(screen.getByTestId("nav-edition-identity")).toHaveTextContent("StoryLens Pro");
    expect(screen.getByTestId("license-pro-status-heading")).toHaveTextContent("专业版已激活");
    expect(screen.queryByText("StoryLens Pro 已激活")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("capability-pending").length).toBeGreaterThan(0);
  });

  it("shows soft error when entitlement fails", async () => {
    entitlementMode = "error";
    wrapShell();
    await waitFor(() => {
      expect(screen.getByTestId("nav-edition-error")).toHaveTextContent(
        "暂时无法读取专业版授权状态。",
      );
    });
    expect(screen.getByTestId("app-edition-badge")).toHaveTextContent("免费版");
  });
});
