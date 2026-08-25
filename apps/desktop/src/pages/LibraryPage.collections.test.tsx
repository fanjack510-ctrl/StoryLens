import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LibraryPage } from "./LibraryPage";
import { useOnboardingStore } from "../stores/onboardingStore";

/** 书单：一组可以被反复回到的书。
 *
 *  扫榜是「一次过十几本新书、横着比」。那批书需要一个名字才能被反复回到。
 *
 *  **但书单不再是书库首页上的一行。**用户看完的原话是「这里两个书单是什么意思？
 *  为啥上来要建书单？这个功能最终不就是为了提炼共性，那是不是应该统一在共性分析大功能下？」
 *  他是对的：一个刚装好、一个书单都没有的库里，那两行合起来只干了一件事，
 *  催他去建一个还不知道有什么用的东西。圈书搬去了共性视图页（见
 *  `CommonPatternsStartPage.test.tsx`），这里只剩两件事：
 *   1. 存过组的人能「只看某一组」——降级进「更多筛选」，没存过的人看不见这个词
 *   2. 勾几本一次性加进已有的组
 */
const list = vi.fn();
const library = vi.fn();
const collectionsList = vi.fn();
const collectionsRead = vi.fn();
const collectionsCreate = vi.fn();
const collectionsAdd = vi.fn();

vi.mock("../services/booksApi", () => ({
  booksApi: {
    list: (...a: unknown[]) => list(...a),
    library: (...a: unknown[]) => library(...a),
    preview: vi.fn(),
    importFile: vi.fn(),
  },
}));

vi.mock("../services/collectionsApi", () => ({
  collectionsApi: {
    list: (...a: unknown[]) => collectionsList(...a),
    read: (...a: unknown[]) => collectionsRead(...a),
    create: (...a: unknown[]) => collectionsCreate(...a),
    addBooks: (...a: unknown[]) => collectionsAdd(...a),
    removeBook: vi.fn(),
    remove: vi.fn(),
    update: vi.fn(),
  },
}));

vi.mock("../components/onboarding/AiSetupBanner", () => ({ AiSetupBanner: () => null }));
vi.mock("../components/onboarding/FirstLaunchWizard", () => ({ FirstLaunchWizard: () => null }));

function book(id: number, title: string) {
  return {
    id,
    title,
    source_file_name: `${title}.txt`,
    source_file_hash: `h${id}`,
    created_at: `2026-08-0${id}T00:00:00`,
    import_status: "imported",
  };
}

function libRow(id: number, title: string) {
  return {
    id,
    title,
    source_file_name: "",
    format: "TXT",
    created_at: `2026-08-0${id}T00:00:00`,
    material_kind: "fiction" as const,
    material_kind_confirmed: true,
    kind_label: "小说 · 长篇",
    chapter_count: 100,
    analysis_state: "idle" as const,
    analysis_state_label: "未分析",
  };
}

function renderLibrary() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <LibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("书库里的书单", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    useOnboardingStore.setState({ status: "completed" });
    list.mockResolvedValue([book(1, "甲书"), book(2, "乙书"), book(3, "丙书")]);
    library.mockResolvedValue([libRow(1, "甲书"), libRow(2, "乙书"), libRow(3, "丙书")]);
    collectionsList.mockResolvedValue([
      { id: 7, name: "2026 秋·扫榜", note: "看开头", book_count: 2, created_at: null, updated_at: null },
    ]);
    collectionsRead.mockResolvedValue({
      id: 7,
      name: "2026 秋·扫榜",
      note: "看开头",
      book_count: 2,
      created_at: null,
      updated_at: null,
      books: [libRow(1, "甲书"), libRow(3, "丙书")],
    });
  });

  it("书单降级进「更多筛选」，不再占首页一行", async () => {
    // 它原来和类型筛选并排，还带一个「+ 新建书单」。对一个还没有任何书单的人，
    // 那一行只是在催他建一个不知道有什么用的东西。
    renderLibrary();
    const sel = await screen.findByTestId("library-collection-filter");
    expect(sel).toBeInTheDocument();
    // 数量写在选项上：不点进去就知道这一组攒了多少本。
    expect(sel).toHaveTextContent("2026 秋·扫榜");
    expect(sel).toHaveTextContent("2");
  });

  it("首页先给真实概览和继续入口，再进入完整书单", async () => {
    library.mockResolvedValue([
      {
        ...libRow(1, "甲书"),
        analysis_state: "done",
        analysis_state_label: "已评测",
        last_activity_at: "2026-08-24T08:00:00Z",
      },
      {
        ...libRow(2, "乙书"),
        analysis_state: "running",
        analysis_state_label: "进行中",
        last_activity_at: "2026-08-24T09:00:00Z",
      },
      libRow(3, "丙书"),
    ]);

    renderLibrary();

    const metrics = await screen.findByTestId("library-home-metrics");
    await waitFor(() => {
      expect(metrics).toHaveTextContent("3全部书籍");
      expect(metrics).toHaveTextContent("1已完成分析");
      expect(metrics).toHaveTextContent("1正在运行");
      expect(metrics).toHaveTextContent("1等待开始");
      expect(metrics).toHaveTextContent("1已存书单");
    });

    const spotlight = await screen.findByTestId("library-spotlight");
    const filters = screen.getByTestId("library-filter-bar");
    expect(spotlight.compareDocumentPosition(filters) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("选中书单后，列表只剩它里面的书", async () => {
    renderLibrary();
    fireEvent.change(await screen.findByTestId("library-collection-filter"), {
      target: { value: "7" },
    });
    await waitFor(() => expect(collectionsRead).toHaveBeenCalledWith(7));
    await waitFor(() => {
      expect(screen.queryByTestId("book-row-2")).toBeNull();
    });
    expect(screen.getByTestId("book-row-1")).toBeInTheDocument();
    expect(screen.getByTestId("book-row-3")).toBeInTheDocument();
  });

  it("没选书时不出现工具条", async () => {
    renderLibrary();
    await screen.findByTestId("book-row-1");
    // 常驻一条空工具条，等于每次进书库都要先看懂一个当下用不上的东西。
    expect(screen.queryByTestId("library-selection-bar")).toBeNull();
  });

  it("勾几本，一次性加进书单", async () => {
    collectionsAdd.mockResolvedValue({ added: 2, book_count: 4 });
    renderLibrary();
    fireEvent.click(await screen.findByTestId("book-pick-1"));
    fireEvent.click(await screen.findByTestId("book-pick-2"));

    const bar = await screen.findByTestId("library-selection-bar");
    expect(bar).toHaveTextContent("已选 2 本");

    fireEvent.change(screen.getByTestId("library-add-to-collection"), {
      target: { value: "7" },
    });
    // 一次请求带上两本，而不是发两次——十五本书要点十五次是这件事做不成的原因。
    await waitFor(() => expect(collectionsAdd).toHaveBeenCalledWith(7, [1, 2]));
  });

  it("加完说清楚加了几本，而不是只说「成功」", async () => {
    // 勾了 2 本、实际加进去 0 本（都已经在里面）时，「成功」这句话解释不了数字为什么没变。
    collectionsAdd.mockResolvedValue({ added: 0, book_count: 2 });
    renderLibrary();
    fireEvent.click(await screen.findByTestId("book-pick-1"));
    fireEvent.change(await screen.findByTestId("library-add-to-collection"), {
      target: { value: "7" },
    });
    const toast = await screen.findByTestId("library-delete-toast");
    expect(toast).toHaveTextContent("都已经在");
  });

  it("空书单说的是「还没有书」，不是「没找到」", async () => {
    // 手点出来的：新建一个书单、自动切进去，列表空着，界面却说「没有找到匹配的书 ·
    // 尝试修改搜索内容或文件格式筛选」。搜索和筛选都没问题，这个单子就是还没放东西——
    // 把一个正常状态说成故障，而且指的方向还是错的。
    collectionsRead.mockResolvedValue({
      id: 7,
      name: "2026 秋·扫榜",
      note: "",
      book_count: 0,
      created_at: null,
      updated_at: null,
      books: [],
    });
    renderLibrary();
    fireEvent.change(await screen.findByTestId("library-collection-filter"), {
      target: { value: "7" },
    });
    const empty = await screen.findByTestId("library-collection-empty");
    expect(empty).toHaveTextContent("还没有书");
    expect(empty).toHaveTextContent("加入书单");
    expect(screen.queryByTestId("library-search-miss")).toBeNull();
    // 出口指向「去挑书」，不是「改筛选」。
    fireEvent.click(screen.getByTestId("library-collection-empty-back"));
    await waitFor(() => expect(screen.queryByTestId("library-collection-empty")).toBeNull());
  });

  it("书库里不再有「新建书单」", () => {
    // 在书库里建一个空书单，等于要求人在还不知道要比什么之前先给一个组命名。
    // 建组的动作搬去了共性视图页：先勾书，再决定这组值不值得留个名字。
    renderLibrary();
    expect(screen.queryByTestId("library-collection-new")).toBeNull();
  });
});
