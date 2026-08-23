import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LibraryPage } from "./LibraryPage";
import { useOnboardingStore } from "../stores/onboardingStore";

/** 书单：一组可以被反复回到的书。
 *
 *  扫榜是「一次过十几本新书、横着比」。那批书需要一个名字才能被反复回到——否则每次都要在
 *  书库里重新挑一遍。这里钉的是「用起来会疼」的地方：一次加一批而不是一本一本、
 *  选中的状态看得见、加进去以后说清楚加了几本。
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

  it("书单和类型筛选并排，是同一层的取景方式", async () => {
    renderLibrary();
    expect(await screen.findByTestId("library-collection-all")).toBeInTheDocument();
    const chip = await screen.findByTestId("library-collection-7");
    expect(chip).toHaveTextContent("2026 秋·扫榜");
    // 数量直接写在标签上：不点进去就知道这个单子攒了多少本。
    expect(chip).toHaveTextContent("2");
  });

  it("选中书单后，列表只剩它里面的书", async () => {
    renderLibrary();
    fireEvent.click(await screen.findByTestId("library-collection-7"));
    await waitFor(() => expect(collectionsRead).toHaveBeenCalledWith(7));
    await waitFor(() => {
      expect(screen.queryByTestId("book-row-2")).toBeNull();
    });
    expect(screen.getByTestId("book-row-1")).toBeInTheDocument();
    expect(screen.getByTestId("book-row-3")).toBeInTheDocument();
  });

  it("共性视图的入口一直在，没选书单时说清缺什么", async () => {
    // 原来是「选中书单才渲染」——后果是一个没建过书单的人永远不会知道共性视图存在：
    // 他得先建单、再选中，那个按钮才第一次出现。一个看不见的功能和不存在没有区别，
    // 而这是要卖钱的功能。
    renderLibrary();
    const bar = await screen.findByTestId("library-collection-actions");
    expect(bar).toHaveTextContent("看这组书的共性");
    // 灰着，但在。并且说的是缺什么，不是「不可用」——前者是一句他能照做的话。
    expect(screen.getByTestId("library-open-patterns-blocked")).toBeInTheDocument();
    expect(screen.queryByTestId("library-open-patterns")).toBeNull();
    // 等书单查询回来之后，文案才该断言「有书单但没选」。
    // 加载中说「先建一个书单」是把「还不知道」当成了「没有」。
    await waitFor(() => expect(bar).toHaveTextContent("先选上面一个书单"));
  });

  it("一个书单都没有时，说的是「先建一个」", async () => {
    // 缺的东西不一样，该说的话就不一样：没书单要先建，有书单要先选。
    collectionsList.mockResolvedValue([]);
    renderLibrary();
    const bar = await screen.findByTestId("library-collection-actions");
    // 同样要等查询回来——加载中的文案是中性的那一句。
    await waitFor(() => expect(bar).toHaveTextContent("先建一个书单"));
  });

  it("选中书单后入口变成可点的", async () => {
    renderLibrary();
    fireEvent.click(await screen.findByTestId("library-collection-7"));
    await waitFor(() =>
      expect(screen.getByTestId("library-open-patterns")).toHaveAttribute(
        "href",
        "/collections/7/patterns",
      ),
    );
    expect(screen.queryByTestId("library-open-patterns-blocked")).toBeNull();
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
    fireEvent.click(await screen.findByTestId("library-collection-7"));
    const empty = await screen.findByTestId("library-collection-empty");
    expect(empty).toHaveTextContent("还没有书");
    expect(empty).toHaveTextContent("加入书单");
    expect(screen.queryByTestId("library-search-miss")).toBeNull();
    // 出口指向「去挑书」，不是「改筛选」。
    fireEvent.click(screen.getByTestId("library-collection-empty-back"));
    await waitFor(() => expect(screen.queryByTestId("library-collection-empty")).toBeNull());
  });

  it("新建书单用内联表单，建完直接切进去", async () => {
    collectionsCreate.mockResolvedValue({
      id: 9,
      name: "新单子",
      note: "",
      book_count: 0,
      created_at: null,
      updated_at: null,
    });
    collectionsRead.mockResolvedValue({
      id: 9,
      name: "新单子",
      note: "",
      book_count: 0,
      created_at: null,
      updated_at: null,
      books: [],
    });
    renderLibrary();
    fireEvent.click(await screen.findByTestId("library-collection-new"));
    const form = await screen.findByTestId("library-collection-form");
    fireEvent.change(form.querySelector("input") as HTMLInputElement, {
      target: { value: "新单子" },
    });
    fireEvent.submit(form);
    await waitFor(() => expect(collectionsCreate).toHaveBeenCalledWith({ name: "新单子" }));
    // 新建书单几乎总是为了马上往里放书——建完停在原地，用户还得再点一次。
    await waitFor(() => expect(collectionsRead).toHaveBeenCalledWith(9));
  });
});
