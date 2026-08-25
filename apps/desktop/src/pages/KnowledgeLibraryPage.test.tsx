import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { KnowledgeLibraryPage } from "./KnowledgeLibraryPage";
import { ApiError } from "../services/apiClient";

const librarySummary = vi.fn();
const librarySources = vi.fn();
const materials = vi.fn();
const genres = vi.fn();
const extractLibrarySource = vi.fn();
const generateBookSkill = vi.fn();

vi.mock("../services/materialLabApi", () => ({
  materialLabApi: {
    librarySummary: (...args: unknown[]) => librarySummary(...args),
    librarySources: (...args: unknown[]) => librarySources(...args),
    materials: (...args: unknown[]) => materials(...args),
    genres: (...args: unknown[]) => genres(...args),
    extractLibrarySource: (...args: unknown[]) => extractLibrarySource(...args),
    generateBookSkill: (...args: unknown[]) => generateBookSkill(...args),
  },
}));

vi.mock("../components/ui/ProTag", () => ({
  ProTag: () => <span>PRO</span>,
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><KnowledgeLibraryPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => cleanup());

describe("独立题材知识库", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    librarySummary.mockResolvedValue({
      knowledge_count: 30,
      extracted_knowledge_count: 30,
      imported_knowledge_count: 0,
      source_book_count: 1,
      legacy_source_book_count: 0,
      by_role: { genre_example: 30, domain_reference: 0 },
      by_genre: [{ slug: "xuanyi", label: "悬疑", count: 30 }],
      by_category: [{ key: "clue_object", label: "实物线索", count: 10 }],
      taxonomy: [{
        slug: "xuanyi",
        label: "悬疑",
        count: 30,
        categories: [
          { key: "opening_anomaly", label: "开篇异常", count: 20 },
          { key: "clue_object", label: "实物线索", count: 10 },
        ],
      }],
      sources: [],
    });
    librarySources.mockResolvedValue({
      total: 1,
      items: [{
        book_id: 8,
        book_title: "雾港疑案",
        breakdown_run_id: 81,
        breakdown_completed_at: "2026-08-24T08:00:00Z",
        material_count: 30,
        genre_slug: "xuanyi",
        extracted: true,
      }],
    });
    genres.mockResolvedValue({ items: [{ slug: "xuanyi", label: "悬疑", category_count: 18 }] });
    extractLibrarySource.mockResolvedValue({ materials: 30 });
    generateBookSkill.mockResolvedValue({
      schema_version: "storylens-book-skill/1.0",
      filename: "storylens-book-8-SKILL.md",
      skill_name: "storylens-book-8",
      book_id: 8,
      source_run_id: 81,
      source_title: "雾港疑案",
      content: "---\nname: storylens-book-8\n---\n# 作品机制迁移 Skill\n",
      sections: ["使用边界", "结构迁移模板"],
    });
    materials.mockResolvedValue({
      total: 1,
      items: [{
        id: 1,
        origin: "whole_book",
        book_id: 8,
        source_book_title: "雾港疑案",
        chapter_id: 80,
        scene_seq: 1,
        place: "",
        time_cue: "",
        genre_slug: "xuanyi",
        material_type: "线索",
        category_key: "clue_object",
        category_label: "实物线索",
        subcategory_key: "suspicious",
        subcategory_label: "可疑物证",
        title: "没有登记的戒指",
        source_excerpt: "一枚戒指压在案件记录下面，档案里没有登记。",
        source_paragraph_ids: ["B0008-C0001-P0003"],
        source_material_kind: "fiction",
        source_material_kind_confirmed: true,
        knowledge_role: "genre_example",
        knowledge_role_label: "题材案例",
        verification_label: "原文可核对，但不能作为事实依据",
        concise_example: "",
        core_pattern: "",
        mechanism: "",
        suspense_question: "",
        applicable_stage: "",
        applicable_scene: "",
        emotion: "",
        tags: ["悬疑", "物证"],
        quality_score: 80,
        confidence: 0.8,
        pattern_id: 1,
        is_primary_variant: true,
      }],
    });
  });

  it("只列全文拆完的小说，并从全局页面重新提取", async () => {
    renderPage();
    expect(await screen.findByText("创作知识库")).toBeInTheDocument();
    expect(screen.getByTestId("knowledge-workspace-materials")).toHaveTextContent("素材知识");
    expect(screen.getByTestId("knowledge-workspace-patterns")).toHaveTextContent("榜单共性");
    expect(screen.getByTestId("knowledge-workspace-skill")).toHaveTextContent("作品 Skill");
    fireEvent.click(screen.getByText("管理全书来源"));
    expect(await screen.findByTestId("knowledge-source-8")).toHaveTextContent("全文拆文已完成");

    fireEvent.click(screen.getByRole("button", { name: /重新提取/ }));
    await waitFor(() => expect(extractLibrarySource).toHaveBeenCalledWith(8, "xuanyi"));
  });

  it("免费版提取素材时明确引导购买或激活，不把权限提示伪装成提取失败", async () => {
    extractLibrarySource.mockRejectedValue(new ApiError(
      "PRO_FEATURE_REQUIRED",
      "从全文拆文结果提取素材需要 StoryLens Pro。",
      403,
      { afdian_product_url: "https://afdian.com/item/demo" },
    ));
    renderPage();
    fireEvent.click(await screen.findByText("管理全书来源"));
    fireEvent.click(screen.getByRole("button", { name: /重新提取/ }));

    const notice = await screen.findByTestId("knowledge-pro-required");
    expect(notice).toHaveTextContent("需要 StoryLens Pro");
    expect(notice).toHaveTextContent("前往爱发电购买");
    expect(screen.getByRole("link", { name: "已有授权码，去激活" })).toHaveAttribute(
      "href",
      "/settings?tab=license",
    );
  });

  it("全文来源很多时按六本分页，并可按书名和提取状态快速缩小范围", async () => {
    librarySources.mockResolvedValue({
      total: 15,
      items: Array.from({ length: 15 }, (_, index) => ({
        book_id: index + 1,
        book_title: `来源${String(index + 1).padStart(2, "0")}`,
        breakdown_run_id: 100 + index,
        breakdown_completed_at: "2026-08-24T08:00:00Z",
        material_count: (index + 1) % 2 === 0 ? 12 : 0,
        genre_slug: "xuanyi",
        extracted: (index + 1) % 2 === 0,
      })),
    });
    renderPage();
    fireEvent.click(await screen.findByText("管理全书来源"));

    expect(await screen.findByTestId("knowledge-source-1")).toBeInTheDocument();
    expect(screen.getByTestId("knowledge-source-6")).toBeInTheDocument();
    expect(screen.queryByTestId("knowledge-source-7")).not.toBeInTheDocument();
    expect(screen.getByText("1 / 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    expect(screen.getByTestId("knowledge-source-7")).toBeInTheDocument();
    expect(screen.queryByTestId("knowledge-source-1")).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole("searchbox", { name: "搜索全书来源" }), { target: { value: "来源15" } });
    expect(screen.getByTestId("knowledge-source-15")).toBeInTheDocument();
    expect(screen.queryByTestId("knowledge-source-7")).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole("searchbox", { name: "搜索全书来源" }), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "已提取 7" }));
    expect(screen.getAllByText("已提取").length).toBeGreaterThan(0);
    expect(screen.queryByText("待提取", { selector: ".knowledge-source-state" })).not.toBeInTheDocument();
  });

  it("素材来源回正文阅读，不回单书知识页", async () => {
    renderPage();
    expect(await screen.findByText("没有登记的戒指")).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "雾港疑案" }).find(
        (link) => link.getAttribute("href")?.includes("chapter=80"),
      ),
    ).toHaveAttribute("href", "/books/8?chapter=80&view=reading");
    expect(screen.getByText(/B0008-C0001-P0003/)).toBeInTheDocument();
    expect(screen.queryByText("领域资料")).not.toBeInTheDocument();
    expect(screen.getByText("知识分类")).toBeInTheDocument();
    expect(screen.queryByText("可复用模式")).not.toBeInTheDocument();
    expect(screen.queryByText("为什么有效")).not.toBeInTheDocument();
  });

  it("从全文来源生成并下载作品 Skill", async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId("knowledge-workspace-skill"));
    expect(await screen.findByTestId("knowledge-skill-workspace")).toHaveTextContent("全文拆完");
    fireEvent.click(screen.getByTestId("generate-book-skill"));
    await waitFor(() => expect(generateBookSkill).toHaveBeenCalledWith(8));
    expect(await screen.findByTestId("book-skill-result")).toHaveTextContent("storylens-book-8-SKILL.md");
  });

  it("按题材和题材内分类浏览，不显示开发迁移来源", async () => {
    renderPage();
    await screen.findByText("没有登记的戒指");
    expect(screen.queryByText("旧项目资料库")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /悬疑\s*30/ }));
    expect(screen.getByRole("button", { name: /开篇异常\s*20/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /实物线索\s*10/ }));
    await waitFor(() => expect(materials).toHaveBeenLastCalledWith(expect.objectContaining({
      genre_slug: "xuanyi",
      category_key: "clue_object",
    })));
  });

  it("可以从全部知识切换到跨书代表", async () => {
    renderPage();
    await screen.findByText("没有登记的戒指");
    fireEvent.change(screen.getByRole("combobox", { name: "展示范围" }), { target: { value: "primary" } });
    await waitFor(() => expect(materials).toHaveBeenLastCalledWith(expect.objectContaining({ primary_only: true })));
  });

  it("结构化写作资料显示资料依据而不是参考小说", async () => {
    materials.mockResolvedValue({
      total: 1,
      items: [{
        id: "legacy:farming-1",
        origin: "reference_corpus",
        book_id: null,
        source_book_title: "古代种田文写作素材库·第一册",
        chapter_id: null,
        scene_seq: 20,
        place: "",
        time_cue: "",
        genre_slug: "zhongtian",
        material_type: "knowledge",
        category_key: "daily",
        category_label: "日常细节",
        subcategory_key: "household",
        subcategory_label: "家庭分工",
        title: "当家主妇",
        source_excerpt: "生活依据：管理家庭余粮。",
        source_paragraph_ids: ["D-1234567890-S01-I02-BASIS"],
        source_material_kind: "reference",
        source_material_kind_confirmed: true,
        knowledge_role: "domain_reference",
        knowledge_role_label: "种田资料知识",
        verification_label: "本地写作资料 · 农家人物 · 三段资料依据已核对",
        concise_example: "管理家庭余粮。",
        core_pattern: "",
        mechanism: "",
        suspense_question: "",
        applicable_stage: "全书",
        applicable_scene: "农家人物",
        emotion: "种田",
        tags: ["农家人物"],
        quality_score: 96,
        confidence: 0.96,
        pattern_id: "corpus:structured-farming:S01",
        is_primary_variant: true,
      }],
    });

    renderPage();

    expect(await screen.findByText("当家主妇")).toBeInTheDocument();
    expect(screen.getByText("查看资料依据")).toBeInTheDocument();
    expect(screen.queryByText("查看原文依据")).not.toBeInTheDocument();
  });
});
