import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WholeBookV2MockPage } from "./WholeBookV2MockPage";
import { WholeBookV2ProgressMockPage } from "./WholeBookV2ProgressMockPage";
import { buildMockWholeBookAnalysisV2 } from "../wholeBookV2/mockAdapter";
import { modulesForDocument } from "../wholeBookV2/presentation/modules";

afterEach(cleanup);

describe("Whole-Book V2 static mock", () => {
  it("buildMockWholeBookAnalysisV2 passes parseWholeBookV2", () => {
    const data = buildMockWholeBookAnalysisV2();
    expect(data.schema_version).toBe("whole-book-analysis-v2.0");
    expect(data.story.structure_stages.length).toBeGreaterThan(0);
    expect(data.characters.protagonist.stages.length).toBeGreaterThan(0);
    expect(data.pacing.event_markers.length).toBeGreaterThan(0);
  });

  it("uses shared ReportView with seven approved modules", () => {
    render(
      <MemoryRouter>
        <WholeBookV2MockPage />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("whole-book-v2-mock")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-v2-report")).toBeInTheDocument();
    expect(screen.getAllByText("作品画像").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("navigation", { name: "全书分析模块" }).querySelectorAll("button")).toHaveLength(7);
    for (const mod of modulesForDocument(buildMockWholeBookAnalysisV2())) {
      expect(screen.getByRole("button", { name: new RegExp(mod.label) })).toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: /类型专项/ })).not.toBeInTheDocument();
    // 故事骨架 was drawn twice — once as a timeline, once as a list — and is now drawn once,
    // inside 全书脉络. What is worth pinning is not which of the two survived but the property
    // the merge exists for: the overview states each fact once.
    expect(screen.getByText("这本书是怎么走下来的")).toBeInTheDocument();
    const sentence = screen.getByTestId("whole-book-v2-report").textContent ?? "";
    const story = buildMockWholeBookAnalysisV2().overview.one_sentence_story;
    expect(sentence.split(story).length - 1).toBe(1);
  });

  it("story module states its four sections on one page, timeline included", () => {
    render(
      <MemoryRouter>
        <WholeBookV2MockPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /故事/ }));
    // The module used to hold eight facts behind three inner tabs, under an outer bar that
    // is already seven tabs. What is pinned is that a second tier never comes back.
    expect(document.querySelectorAll(".wb2-tabs")).toHaveLength(0);
    for (const h of ["这本书分成几段", "几条线，各自走到哪", "哪件事导致了哪件事", "按章顺序，发生了什么"]) {
      expect(screen.getByText(h)).toBeInTheDocument();
    }
    // chronology has been computed since v2.0 and was never rendered; the page's own
    // description promised 时间线 while showing three of the four things it named.
    const rows = document.querySelectorAll(".wb2-chrono > div");
    expect(rows.length).toBe(buildMockWholeBookAnalysisV2().story.chronology.length);
    expect(rows.length).toBeGreaterThan(0);
    // Told-out-of-order is a fact about the book, so it is stated rather than left implied.
    expect(screen.getByText(/处倒叙|全书顺叙/)).toBeInTheDocument();
  });

  it("character profile shows the record, and roles are not raw enum values", () => {
    render(
      <MemoryRouter>
        <WholeBookV2MockPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /^3人物$|^3 人物$/ }));
    // contracts.ts declared 5 of the 17 fields the engine returns, so the profile card
    // printed a name and a row of evidence ids over an otherwise empty panel.
    const data = buildMockWholeBookAnalysisV2();
    const first = data.characters.major_characters[0];
    const panel = document.querySelector(".wb2-profile");
    expect(panel).not.toBeNull();
    const carries = [
      first.identity,
      first.final_goal,
      first.major_choice,
      first.ending,
      ...(first.key_events ?? []),
    ].filter((x): x is string => Boolean(x && x.trim()));
    expect(carries.length).toBeGreaterThan(0);
    expect((panel?.textContent ?? "").length).toBeGreaterThan(first.name.length + 40);
    // 叙事角色 is shown to a Chinese reader, so it is not the wire value.
    expect(screen.queryByText("protagonist")).not.toBeInTheDocument();
    expect(screen.queryByText("supporting")).not.toBeInTheDocument();
  });

  it("renders pacing and chapters via shared ReportView", () => {
    render(
      <MemoryRouter>
        <WholeBookV2MockPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /节奏/ }));
    expect(screen.getByRole("img", { name: "全书节奏曲线" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /章节/ }));
    expect(screen.getByText(/聚合展示热力图/)).toBeInTheDocument();
  });

  it("renders comprehensive assessment module", () => {
    render(
      <MemoryRouter>
        <WholeBookV2MockPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /综合诊断/ }));
    expect(screen.getByText("六维评估")).toBeInTheDocument();
    expect(screen.getByText("修改优先级")).toBeInTheDocument();
  });

  it("reveals protagonist cost and gain in characters module", () => {
    render(
      <MemoryRouter>
        <WholeBookV2MockPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /^3人物$|^3 人物$/ }));
    fireEvent.click(screen.getByRole("button", { name: "主角历程" }));
    expect(screen.getByText("付出 COST")).toBeInTheDocument();
    expect(screen.getByText("获得 GAIN")).toBeInTheDocument();
  });

  it("PDF export is VIP-gated: a 403 shows the notice and never falls back to HTML", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({
        detail: {
          error_code: "PDF_REQUIRES_VIP",
          message: "PDF 导出是 VIP（Pro）功能。",
          details: { afdian_product_url: "https://afdian.com/item/test-monthly" },
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    // jsdom has no blob-URL support; the download path needs both stubs to be observable.
    if (!URL.createObjectURL) {
      URL.createObjectURL = (() => "blob:mock") as typeof URL.createObjectURL;
      URL.revokeObjectURL = (() => undefined) as typeof URL.revokeObjectURL;
    }
    const clicks: string[] = [];
    const origClick = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function () {
      clicks.push(this.download);
    };
    try {
      render(
        <MemoryRouter>
          <WholeBookV2MockPage />
        </MemoryRouter>,
      );
      fireEvent.click(screen.getByTestId("whole-book-v2-export-button"));
      await waitFor(() => {
        expect(screen.getByTestId("whole-book-v2-vip-notice")).toBeInTheDocument();
      });
      // The refusal is an answer, not an outage: no HTML handed out under the counter.
      expect(clicks).toHaveLength(0);
      expect(screen.getByRole("link", { name: /爱发电/ })).toHaveAttribute(
        "href",
        "https://afdian.com/item/test-monthly",
      );
      // The free HTML export still works on its own button.
      fireEvent.click(screen.getByTestId("whole-book-v2-export-html-button"));
      expect(clicks.some((n) => n.endsWith(".html"))).toBe(true);
    } finally {
      HTMLAnchorElement.prototype.click = origClick;
      vi.unstubAllGlobals();
    }
  });

  it("renders the complete progress surface", () => {
    render(
      <MemoryRouter>
        <WholeBookV2ProgressMockPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("63%")).toBeInTheDocument();
    expect(screen.getByText("最终报告")).toBeInTheDocument();
    expect(screen.getByText("当前累计费用")).toBeInTheDocument();
  });
});
