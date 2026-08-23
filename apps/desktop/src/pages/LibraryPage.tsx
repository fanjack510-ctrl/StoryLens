import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { collectionsApi } from "../services/collectionsApi";
import { booksApi } from "../services/booksApi";
import type { LibraryItem, MaterialKind } from "../services/booksApi";
import type { AnalysisForm } from "../services/shortFormApi";
import { ApiError } from "../services/apiClient";
import { ErrorState, Loading } from "../components/common/States";
import { AiSetupBanner } from "../components/onboarding/AiSetupBanner";
import { FirstLaunchWizard } from "../components/onboarding/FirstLaunchWizard";
import { TelemetryInviteCard } from "../components/onboarding/TelemetryInviteCard";
import { useOnboardingStore } from "../stores/onboardingStore";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { OverflowMenu } from "../components/layout/OverflowMenu";
import { PageHeader, PageSubtitle, PageTitle } from "../components/ui/PageHeader";
import { StateView } from "../components/ui/StateView";
import { isLocalWebShell, useRuntimeInfo } from "../services/runtimeCapabilities";
import type { Book, ImportDiagnostics } from "../types";

// 筛选器要跟得上摄入层。少列一种，用户导进来的书会落进「其他」，一筛就不见了——
// 他会以为导入失败，而它其实好端端地在库里。
const FORMAT_OPTIONS = ["TXT", "DOCX", "EPUB", "PDF", "MD", "TEX", "HTML", "ODT"] as const;
type FormatOption = (typeof FORMAT_OPTIONS)[number];

const EXT_ALIAS: Record<string, FormatOption> = {
  TXT: "TXT", DOCX: "DOCX", EPUB: "EPUB", PDF: "PDF",
  MD: "MD", MARKDOWN: "MD", TEX: "TEX", LATEX: "TEX",
  HTML: "HTML", HTM: "HTML", XHTML: "HTML", ODT: "ODT",
};

function fileFormat(name: string): FormatOption | "OTHER" {
  const ext = name.split(".").pop()?.toUpperCase() ?? "";
  return EXT_ALIAS[ext] ?? "OTHER";
}

function importErrorKind(error: unknown): {
  title: string;
  tone: "danger" | "warning";
} {
  if (error instanceof ApiError) {
    const msg = `${error.code} ${error.message} ${String(error.detail || "")}`.toLowerCase();
    if (error.status === 413 || /过大|too large|size/i.test(msg)) {
      return { title: "文件过大", tone: "danger" };
    }
    if (/编码|encoding/i.test(msg)) {
      return { title: "编码无法识别", tone: "danger" };
    }
    if (/格式|format|不支持|invalid_file_type/i.test(msg)) {
      return { title: "文件格式不支持", tone: "danger" };
    }
    if (
      error.status === 409 ||
      error.code === "DUPLICATE_BOOK" ||
      /重复|duplicate|已存在|已导入/i.test(msg)
    ) {
      return { title: "书籍可能已存在", tone: "warning" };
    }
  }
  return { title: "导入失败", tone: "danger" };
}

/** Say which thing is wrong, not that something is.
 *
 *  The panel used to print one fixed sentence — "文件较大但只识别出一个章节" — for every kind of
 *  failure, and it was usually false: 《碧血洗银枪》 has two chapters and 《最终进化》 has 206. A
 *  warning that misdescribes what it found teaches the reader to dismiss it. */
function describeSuspectReasons(d: ImportDiagnostics): string {
  const reasons = d.suspect_reasons ?? [];
  const said: string[] = [];
  if (reasons.includes("SINGLE_CHAPTER")) said.push("整本书只切出了一章");
  if (reasons.includes("ONE_CHAPTER_DOMINATES") && d.max_chapter_share) {
    said.push(`其中一章占了全书 ${Math.round(d.max_chapter_share * 100)}%`);
  }
  if (reasons.includes("OVERSIZED_CHAPTER")) {
    said.push(`最长的一章有 ${d.max_chapter_characters.toLocaleString()} 字`);
  }
  if (reasons.includes("CHAPTER_TOO_MANY_PARAGRAPHS")) {
    said.push(`最长的一章有 ${d.max_chapter_paragraphs.toLocaleString()} 个自然段`);
  }
  if (reasons.includes("MARKERS_FOUND_BUT_NOT_ADOPTED")) {
    said.push(`找到 ${d.candidate_count} 处疑似章节标题，但都没能采纳`);
  }
  // Older diagnostics carry the warning without the reasons behind it.
  return said.length ? said.join("；") + "。" : "章节标题的格式可能没有被识别。";
}

export function LibraryPage() {
  const onboardingStatus = useOnboardingStore((s) => s.status);
  const [searchParams] = useSearchParams();
  const input = useRef<HTMLInputElement>(null);
  const runtime = useRuntimeInfo();
  const webShell = isLocalWebShell(runtime.data);
  const [search, setSearch] = useState("");
  // 从 FORMAT_OPTIONS 生成，而不是手写一份。手写的那份漏了新格式时不会报错，只会让书悄悄
  // 从列表里消失——那正是最难被发现的一类问题。
  const [formats, setFormats] = useState<Record<FormatOption, boolean>>(
    () => Object.fromEntries(FORMAT_OPTIONS.map((f) => [f, true])) as Record<FormatOption, boolean>,
  );
  const [sort, setSort] = useState<"recent" | "title">("recent");
  const [pendingFile, setPendingFile] = useState<File>();
  //: Which pipeline the reader says this work takes. Seeded from the server's suggestion when
  //: the preview lands, so the common case is still one click, and overridden by them freely —
  //: chapter count decides nothing here any more.
  const [form, setForm] = useState<AnalysisForm>("long");
  const [kind, setKind] = useState<MaterialKind>("fiction");
  const [dragOver, setDragOver] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const qc = useQueryClient();
  const books = useQuery({ queryKey: ["books"], queryFn: booksApi.list });
  // 类型、章节数、分析状态由后端算好（INV-P4）——「已评测 / 读懂·进行中」怎么说，
  // 取决于引擎与运行状态的对应关系，那是后端的知识。
  const library = useQuery({ queryKey: ["library"], queryFn: booksApi.library });
  const [kindFilter, setKindFilter] = useState<"all" | "fiction" | "reference" | "idle">("all");
  // 书单：一组可以被反复回到的书。扫榜是「一次过十几本、横着比」，那批书需要一个名字，
  // 否则每次都要在书库里重新挑一遍，而「上次那批」这句话根本无法表达。
  const collections = useQuery({ queryKey: ["collections"], queryFn: collectionsApi.list });
  //: null = 不按书单筛。选中某个书单时，列表只剩它里面的书。
  const [collectionFilter, setCollectionFilter] = useState<number | null>(null);
  //: 勾中的书。选够了再一次性加进书单——一本一本加，十五本要点十五次。
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const [collectionError, setCollectionError] = useState<string | null>(null);
  const [newCollectionOpen, setNewCollectionOpen] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const activeCollection = useQuery({
    queryKey: ["collection", collectionFilter],
    queryFn: () => collectionsApi.read(collectionFilter as number),
    enabled: collectionFilter != null,
  });
  const upload = useMutation({
    mutationFn: (input: { file: File; form: AnalysisForm; kind: MaterialKind }) =>
      booksApi.importFile(input.file, input.form, input.kind),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["books"] });
      void qc.invalidateQueries({ queryKey: ["library"] });
    },
  });
  const preview = useMutation({
    mutationFn: booksApi.preview,
    onSuccess: (data) => {
      const suggested: MaterialKind =
        data.suggested_material_kind === "reference" ? "reference" : "fiction";
      setKind(suggested);
      // 工具书按节读，没有短篇这一说——直接落到长篇，第二步也不会出现。
      setForm(
        suggested === "fiction" &&
          data.suggested_analysis_form === "short" &&
          data.short_form_allowed !== false
          ? "short"
          : "long",
      );
    },
  });
  const accept = (files: FileList | null) => {
    const file = files?.[0];
    if (file) {
      setPendingFile(file);
      preview.mutate(file);
    }
  };
  const clearImport = () => {
    setPendingFile(undefined);
    preview.reset();
    upload.reset();
    if (input.current) input.current.value = "";
  };

  const libraryById = useMemo(
    () => new Map((library.data || []).map((item) => [item.id, item])),
    [library.data],
  );

  const collectionBookIds = useMemo(
    () => new Set((activeCollection.data?.books || []).map((b) => b.id)),
    [activeCollection.data],
  );

  const visible = useMemo(() => {
    const list = (books.data || []).filter((book) => {
      const hay = book.title + book.source_file_name;
      if (search && !hay.includes(search)) return false;
      const info = libraryById.get(book.id);
      if (kindFilter === "fiction" && info?.material_kind !== "fiction") return false;
      if (kindFilter === "reference" && info?.material_kind !== "reference") return false;
      if (kindFilter === "idle" && info?.analysis_state !== "idle") return false;
      if (collectionFilter != null && !collectionBookIds.has(book.id)) return false;
      const fmt = fileFormat(book.source_file_name);
      if (fmt === "OTHER") return true;
      return formats[fmt];
    });
    const sorted = [...list];
    if (sort === "title") {
      sorted.sort((a, b) => a.title.localeCompare(b.title, "zh"));
    } else {
      sorted.sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at));
    }
    return sorted;
  }, [books.data, search, formats, sort, kindFilter, libraryById, collectionFilter, collectionBookIds]);

  // 书库的一句话现状。没读到列表时退回旧的说明句，不显示一个假的「0 本」。
  const librarySummary = useMemo(() => {
    const rows = library.data;
    if (!rows || rows.length === 0) return "管理已导入的书和分析项目";
    const analysed = rows.filter((r) => r.analysis_state === "done").length;
    const running = rows.filter((r) => r.analysis_state === "running").length;
    return [
      `${rows.length} 本`,
      analysed > 0 ? `${analysed} 本已分析` : null,
      running > 0 ? `${running} 本进行中` : null,
    ]
      .filter(Boolean)
      .join(" · ");
  }, [library.data]);

  const hasActiveFilter =
    Boolean(search) ||
    kindFilter !== "all" ||
    collectionFilter != null ||
    !FORMAT_OPTIONS.every((f) => formats[f]);
  const isEmptyLibrary = !books.isLoading && !books.error && (books.data?.length ?? 0) === 0;
  const listHasRows = visible.length > 0;

  useEffect(() => {
    if (searchParams.get("import") === "1") {
      input.current?.click();
    }
  }, [searchParams]);

  const chapterPreviewLimit = 8;
  const previewTitles = preview.data?.chapter_titles || [];
  const moreChapters = Math.max(0, (preview.data?.final_chapter_count || 0) - chapterPreviewLimit);

  return (
    <section className="page library-page-compact" data-testid="library-page">
      {onboardingStatus === "pending" && <FirstLaunchWizard />}
      {onboardingStatus !== "pending" && <TelemetryInviteCard />}
      <AiSetupBanner />
      <PageHeader className="library-title-compact">
        <div>
          <PageTitle>我的书库</PageTitle>
          {/* 「管理已导入的书和分析项目」是一句说明书——它对每个人、每一天说的都一样。
              换成当下真实的数字：有几本，跑过几本。 */}
          <PageSubtitle data-testid="library-subtitle">{librarySummary}</PageSubtitle>
          {webShell ? (
            <p className="muted library-local-upload-hint" data-testid="library-local-upload-hint">
              文件仅发送到本机 StoryLens 服务，不会上传互联网。
            </p>
          ) : null}
        </div>
        <Button
          variant="primary"
          data-testid="import-book"
          onClick={() => input.current?.click()}
        >
          导入书籍
        </Button>
        <input
          ref={input}
          hidden
          type="file"
          accept=".txt,.docx,.epub,.pdf,.md,.markdown,.tex,.latex,.html,.htm,.odt"
          onChange={(event) => accept(event.target.files)}
        />
      </PageHeader>

      {preview.isPending && (
        <div className="import-panel import-panel--info" data-testid="import-panel-parsing">
          <h2>正在解析文件</h2>
          <p>正在提取文本并识别章节，请稍候…</p>
          <Loading />
        </div>
      )}
      {preview.error && (
        <div
          className={`import-panel import-panel--${importErrorKind(preview.error).tone}`}
          data-testid="import-panel-error"
          role="alert"
        >
          <ErrorState
            error={preview.error as Error}
            title={importErrorKind(preview.error).title}
          />
          <div className="import-panel-actions">
            <Button variant="secondary" onClick={clearImport}>
              重新选择文件
            </Button>
          </div>
        </div>
      )}
      {preview.data && pendingFile && (
        <div
          className={`import-panel ${
            preview.data.warning === "CHAPTER_DETECTION_SUSPECT"
              ? "import-panel--warning"
              : "import-panel--success"
          }`}
          data-testid="import-panel"
        >
          <h2>文件已解析</h2>
          <p className="import-panel-file">
            <strong>{pendingFile.name}</strong>
            <span>
              {fileFormat(pendingFile.name)} · {preview.data.encoding.toUpperCase()} ·{" "}
              {(preview.data.byte_count / 1024 / 1024).toFixed(2)} MB
            </span>
          </p>
          {/* 这块提示是按小说的章号格式校准的。工具书按节读，识别不到「第几章」不是问题——
              一本 1603 页的手册照样挨这套警告，只会让人以为文件有毛病。 */}
          {preview.data.warning === "CHAPTER_DETECTION_SUSPECT" && kind === "fiction" ? (
            <div className="notice" role="status">
              <p>
                <b>识别出 {preview.data.final_chapter_count} 个章节，但看起来不对：</b>
                {describeSuspectReasons(preview.data)}
              </p>
              <p>
                后面的分析全部按章计算，分错了会一路算错且不会报错。
                <b>请对照下面的格式看一眼原文件</b>——改好再传，比让程序猜要准。
              </p>
              {preview.data.supported_chapter_formats?.length ? (
                <ul className="import-formats">
                  {preview.data.supported_chapter_formats.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : null}
              <p className="muted">本来就不分章的作品，可以直接继续导入。</p>
            </div>
          ) : (
            <p role="status">已识别 {preview.data.final_chapter_count} 个章节</p>
          )}
          <ol className="import-chapter-list">
            {previewTitles.slice(0, chapterPreviewLimit).map((title, index) => (
              <li key={`${index}-${title}`}>
                <span className="import-chapter-index">{String(index + 1).padStart(2, "0")}</span>
                {title}
              </li>
            ))}
          </ol>
          {moreChapters > 0 && <p className="muted">还有 {moreChapters} 个章节</p>}
          <fieldset className="import-choice" data-testid="import-material-kind">
            <legend>这是什么书？</legend>
            <p className="muted">它决定这本书能用哪几种读法。导入后随时可以改。</p>
            <div className="import-choice-options" role="radiogroup">
              {(
                [
                  { value: "fiction", title: "小说", hint: "网文、出版书、同人都算。能做评测与拆文。" },
                  {
                    value: "reference",
                    title: "工具书",
                    hint: "专著、教材、手册、论文集。做「读懂」——逐节给出主张、依据与能照做的动作。",
                  },
                ] as const
              ).map((option) => (
                <label
                  key={option.value}
                  className={`import-choice-option${kind === option.value ? " is-chosen" : ""}`}
                >
                  <input
                    type="radio"
                    name="material-kind"
                    value={option.value}
                    checked={kind === option.value}
                    onChange={() => {
                      setKind(option.value);
                      if (option.value === "reference") setForm("long");
                    }}
                  />
                  <span className="import-choice-option__title">{option.title}</span>
                  <span className="import-choice-option__hint">{option.hint}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {/* 长短篇只对小说才是个问题。工具书永远按节读——问它「要不要按场景切段」没有意义。 */}
          {kind === "fiction" ? (
            <fieldset className="import-choice" data-testid="import-analysis-form">
              <legend>长篇还是短篇？</legend>
              <p className="muted">
                识别到几章不参与这个判断——你手里拿着文件，比程序清楚。导入后随时可以改。
              </p>
              <div className="import-choice-options" role="radiogroup">
                {(
                  [
                    { value: "long", title: "长篇", hint: "分章读，出全书报告。" },
                    { value: "short", title: "短篇", hint: "按场景切段，出逐段拆稿。" },
                  ] as const
                ).map((option) => {
                  // 短篇有硬上限：切段要把全文一次发给模型，过了就装不下。变灰并说出原因，
                  // 而不是让它消失——一个无声消失的选项读起来像 bug。
                  const blocked =
                    option.value === "short" && preview.data?.short_form_allowed === false;
                  return (
                    <label
                      key={option.value}
                      className={`import-choice-option${form === option.value ? " is-chosen" : ""}${
                        blocked ? " is-blocked" : ""
                      }`}
                    >
                      <input
                        type="radio"
                        name="analysis-form"
                        value={option.value}
                        checked={form === option.value}
                        disabled={blocked}
                        onChange={() => setForm(option.value)}
                      />
                      <span className="import-choice-option__title">{option.title}</span>
                      <span className="import-choice-option__hint">
                        {blocked
                          ? `超过 ${(preview.data?.hard_max_chars ?? 150000).toLocaleString()} 字，不能按短篇读——切段要把全文一次发给模型，装不下`
                          : option.hint}
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ) : null}
          <div className="import-panel-actions">
            {preview.data.warning === "CHAPTER_DETECTION_SUSPECT" ? (
              <>
                <Button
                  variant="primary"
                  onClick={() => {
                    upload.mutate({ file: pendingFile, form, kind });
                    setPendingFile(undefined);
                    preview.reset();
                  }}
                >
                  继续导入
                </Button>
                <Button variant="secondary" onClick={clearImport}>
                  重新选择文件
                </Button>
              </>
            ) : (
              <Button
                variant="primary"
                onClick={() => {
                  upload.mutate({ file: pendingFile, form, kind });
                  setPendingFile(undefined);
                  preview.reset();
                }}
              >
                完成导入
              </Button>
            )}
          </div>
        </div>
      )}

      <div className="library-filter-bar" data-testid="library-filter-bar">
        <label className="library-search-field">
          <span className="sr-only">搜索</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索书名或文件名"
            data-testid="library-search"
          />
        </label>
        {/* 八个格式勾选框原本独占一整行，而它们不是每次都要动的东西。真正每次都想筛的是
            「小说还是工具书」「哪些还没跑」。格式筛选留在「更多筛选」里。 */}
        <div className="library-kind-filter" role="group" aria-label="类型">
          {(
            [
              { id: "all", label: "全部" },
              { id: "fiction", label: "小说" },
              { id: "reference", label: "工具书" },
              { id: "idle", label: "未分析" },
            ] as const
          ).map((chip) => (
            <button
              key={chip.id}
              type="button"
              className="library-kind-chip"
              data-on={kindFilter === chip.id ? "1" : undefined}
              data-testid={`library-kind-${chip.id}`}
              onClick={() => setKindFilter(chip.id)}
            >
              {chip.label}
            </button>
          ))}
        </div>
        {/* 书单条。放在类型筛选旁边而不是另开一页：书单是看书库的一种取景方式，
            不是一个独立的地方——分成两页，用户要在两处之间来回对照才知道哪本在哪个单子里。 */}
        <div className="library-collections" role="group" aria-label="书单">
          <button
            type="button"
            className="library-kind-chip"
            data-on={collectionFilter == null ? "1" : undefined}
            data-testid="library-collection-all"
            onClick={() => setCollectionFilter(null)}
          >
            全部书
          </button>
          {(collections.data || []).map((c) => (
            <button
              key={c.id}
              type="button"
              className="library-kind-chip"
              data-on={collectionFilter === c.id ? "1" : undefined}
              data-testid={`library-collection-${c.id}`}
              title={c.note || undefined}
              onClick={() => setCollectionFilter(collectionFilter === c.id ? null : c.id)}
            >
              {c.name}
              <i className="library-collection-count">{c.book_count}</i>
            </button>
          ))}
          {newCollectionOpen ? (
            <form
              className="library-collection-form"
              data-testid="library-collection-form"
              onSubmit={async (e) => {
                e.preventDefault();
                const name = newCollectionName.trim();
                if (!name) return;
                setCollectionError(null);
                try {
                  const created = await collectionsApi.create({ name });
                  await qc.invalidateQueries({ queryKey: ["collections"] });
                  setNewCollectionName("");
                  setNewCollectionOpen(false);
                  // 建完直接切进去：新建书单几乎总是为了马上往里放书。
                  setCollectionFilter(created.id);
                } catch (err) {
                  setCollectionError(err instanceof ApiError ? err.message : "书单没能建起来。");
                }
              }}
            >
              <input
                autoFocus
                value={newCollectionName}
                placeholder="书单名，比如「2026 秋·扫榜第一批」"
                aria-label="书单名"
                maxLength={120}
                onChange={(e) => setNewCollectionName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setNewCollectionOpen(false);
                    setNewCollectionName("");
                  }
                }}
              />
              <button type="submit" disabled={!newCollectionName.trim()}>
                建立
              </button>
              <button
                type="button"
                className="is-quiet"
                onClick={() => {
                  setNewCollectionOpen(false);
                  setNewCollectionName("");
                }}
              >
                取消
              </button>
            </form>
          ) : (
            <button
              type="button"
              className="library-collection-new"
              data-testid="library-collection-new"
              onClick={() => setNewCollectionOpen(true)}
            >
              + 新建书单
            </button>
          )}
        </div>
        {/* 选中某个书单时才出现。共性视图比的是一组书——不先圈定是哪一组，这个入口没有意义。 */}
        {collectionFilter != null ? (
          <div className="library-collection-actions" data-testid="library-collection-actions">
            <Link
              className="secondary"
              to={`/collections/${collectionFilter}/patterns`}
              data-testid="library-open-patterns"
            >
              看这组书的共性 →
            </Link>
            <span className="muted">
              把它们摆在一起，看共同做对了什么。
            </span>
          </div>
        ) : null}
        {collectionError ? (
          <p className="notice" role="alert" data-testid="library-collection-error">
            {collectionError}
          </p>
        ) : null}
        <details className="library-format-fold">
          <summary>更多筛选</summary>
          <div className="library-filter-types" role="group" aria-label="格式">
            {FORMAT_OPTIONS.map((type) => (
              <label key={type} className="library-format-chip">
                <input
                  type="checkbox"
                  checked={formats[type]}
                  onChange={(e) => setFormats((prev) => ({ ...prev, [type]: e.target.checked }))}
                />
                <span>{type}</span>
              </label>
            ))}
          </div>
        </details>
        <label className="library-sort-field">
          排序
          <select
            data-testid="library-sort"
            value={sort}
            onChange={(e) => setSort(e.target.value as "recent" | "title")}
          >
            <option value="recent">最近导入</option>
            <option value="title">书名</option>
          </select>
        </label>
      </div>

      <div
        className={`panel library-main library-main-wide ${
          isEmptyLibrary ? "library-main--empty" : listHasRows ? "library-main--populated" : ""
        }${dragOver ? " is-drag-over" : ""}`}
        data-testid="library-list"
        data-drag-active={dragOver ? "true" : "false"}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
          setDragOver(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragOver(false);
          accept(event.dataTransfer.files);
        }}
      >
        {upload.isPending && (
          <div className="import-panel import-panel--info import-progress">
            <b>正在导入</b>
            <span>上传文件 → 文本提取 → 章节识别 → 段落编号 → 入库</span>
          </div>
        )}
        {upload.error && (
          <div
            className={`import-panel import-panel--${importErrorKind(upload.error).tone}`}
            role="alert"
            data-testid={
              importErrorKind(upload.error).title === "书籍可能已存在"
                ? "import-duplicate-alert"
                : "import-upload-error"
            }
          >
            <h2>{importErrorKind(upload.error).title}</h2>
            <ErrorState error={upload.error as Error} />
            <div className="import-panel-actions">
              <Button variant="secondary" onClick={clearImport}>
                重新选择文件
              </Button>
            </div>
          </div>
        )}
        {toast ? (
          <p className="notice library-delete-toast" role="status" data-testid="library-delete-toast">
            {toast}
          </p>
        ) : null}
        {/* 选了书才出现。常驻一条空工具条，等于每次进书库都要先看懂一个当下用不上的东西。 */}
        {selected.size > 0 ? (
          <div className="library-selection-bar" data-testid="library-selection-bar">
            <b>已选 {selected.size} 本</b>
            {(collections.data || []).length > 0 ? (
              <label className="library-selection-add">
                加入书单
                <select
                  value=""
                  data-testid="library-add-to-collection"
                  onChange={async (e) => {
                    const id = Number(e.target.value);
                    e.currentTarget.value = "";
                    if (!id) return;
                    setCollectionError(null);
                    try {
                      const result = await collectionsApi.addBooks(id, [...selected]);
                      const name =
                        (collections.data || []).find((c) => c.id === id)?.name ?? "书单";
                      // 说清楚「加了几本」而不是「成功」：勾了 5 本、实际加进去 2 本
                      // （另外 3 本早就在里面）时，「成功」这句话解释不了数字为什么没变。
                      setToast(
                        result.added > 0
                          ? `${result.added} 本已加入《${name}》，现在共 ${result.book_count} 本。`
                          : `这些书都已经在《${name}》里了。`,
                      );
                      setSelected(new Set());
                      await qc.invalidateQueries({ queryKey: ["collections"] });
                      await qc.invalidateQueries({ queryKey: ["collection"] });
                    } catch (err) {
                      setCollectionError(
                        err instanceof ApiError ? err.message : "没能加进书单。",
                      );
                    }
                  }}
                >
                  <option value="">选一个书单…</option>
                  {(collections.data || []).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}（{c.book_count}）
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <span className="muted">先在上面建一个书单，再把选中的书放进去。</span>
            )}
            {collectionFilter != null ? (
              <button
                type="button"
                className="is-quiet"
                data-testid="library-remove-from-collection"
                onClick={async () => {
                  setCollectionError(null);
                  try {
                    for (const id of selected) {
                      await collectionsApi.removeBook(collectionFilter, id);
                    }
                    setToast(`${selected.size} 本已移出这个书单——书还在书库里。`);
                    setSelected(new Set());
                    await qc.invalidateQueries({ queryKey: ["collections"] });
                    await qc.invalidateQueries({ queryKey: ["collection"] });
                  } catch (err) {
                    setCollectionError(
                      err instanceof ApiError ? err.message : "没能从书单里移出。",
                    );
                  }
                }}
              >
                移出当前书单
              </button>
            ) : null}
            <button type="button" className="is-quiet" onClick={() => setSelected(new Set())}>
              取消选择
            </button>
          </div>
        ) : null}
        {books.isLoading ? (
          <Loading />
        ) : books.error ? (
          <ErrorState error={books.error} />
        ) : visible.length > 0 ? (
          visible.map((book) => (
            <BookRow
              key={book.id}
              book={book}
              info={libraryById.get(book.id)}
              selected={selected.has(book.id)}
              onSelectedChange={(next) =>
                setSelected((prev) => {
                  const copy = new Set(prev);
                  if (next) copy.add(book.id);
                  else copy.delete(book.id);
                  return copy;
                })
              }
              onDeleted={(deleted) => {
                setToast(`《${deleted.title}》已从书库删除。`);
                qc.setQueryData<Book[]>(["books"], (prev) =>
                  (prev || []).filter((item) => item.id !== deleted.id),
                );
                void qc.invalidateQueries({ queryKey: ["books"] });
              }}
            />
          ))
        ) : collectionFilter != null && collectionBookIds.size === 0 ? (
          // 空书单不是「没找到」。搜索和筛选都没问题，这个单子就是还没放东西——
          // 让人去「修改搜索内容」，是把一个正常状态说成了故障，而且指的方向还是错的。
          <div className="library-empty-guide" data-testid="library-collection-empty">
            <StateView
              kind="empty"
              title={`《${activeCollection.data?.name ?? "这个书单"}》还没有书`}
              description="回到「全部书」，勾选几本，用工具条上的「加入书单」放进来。"
              data-testid="library-collection-empty-state"
              primaryAction={{
                label: "去全部书里挑",
                onClick: () => setCollectionFilter(null),
                variant: "secondary",
                testId: "library-collection-empty-back",
              }}
            />
          </div>
        ) : books.data && books.data.length > 0 ? (
          <div className="library-empty-guide" data-testid="library-search-miss">
            <StateView
              kind="empty"
              title="没有找到匹配的书"
              description="尝试修改搜索内容或文件格式筛选。"
              data-testid="library-search-miss-state"
              primaryAction={
                hasActiveFilter
                  ? {
                      label: "清除筛选",
                      onClick: () => {
                        setSearch("");
                        setFormats(
                          Object.fromEntries(FORMAT_OPTIONS.map((f) => [f, true])) as Record<
                            FormatOption,
                            boolean
                          >,
                        );
                      },
                      variant: "secondary",
                      testId: "library-clear-filters",
                    }
                  : undefined
              }
            />
          </div>
        ) : (
          <div className="library-empty-guide" data-testid="library-empty-guide">
            <StateView
              kind="empty"
              title="还没有导入书籍"
              description="支持 TXT、DOCX 和 EPUB。导入后即可识别章节并开始分析。"
              data-testid="library-empty-state"
              primaryAction={{
                label: "导入第一本书",
                onClick: () => input.current?.click(),
                testId: "library-empty-import",
              }}
            />
            <div className="drop-hint">也可以将文件拖到这里</div>
          </div>
        )}
        {/* 常驻的虚线拖放框去掉了：它是开发期的提示物。这句话只在真的拖着文件时出现——
            那才是它有用的一刻，其余时间它只是占着位置。 */}
        {dragOver && listHasRows ? (
          <div className="library-drop-overlay" data-testid="library-drop-overlay">
            <b>松手即可导入</b>
            <span>支持 TXT、DOCX、EPUB</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}

/** 书脊的颜色。
 *
 *  书库里原来每一行左边都是同一个「SL」灰方块——七本书七个一模一样的占位符，
 *  眼睛沿着左边扫下去得不到任何区分，这正是「还没填真东西」的样子。
 *
 *  颜色由书名派生，所以同一本书永远是同一个颜色，导入即有、不用管、换机器也一样。
 *  色相在整个圆周上取，饱和度和明度固定在一档能压住白字的区间——不追求好看，
 *  追求的是七本书摆在一起时七种颜色互相分得开。
 */
function spineColor(title: string): string {
  let hash = 2166136261;
  for (let i = 0; i < title.length; i += 1) {
    hash = Math.imul(hash ^ title.charCodeAt(i), 16777619) >>> 0;
  }
  // 雪崩一下再取色相。少了这几步，两本书名只差几个字的书会拿到几乎一样的颜色——
  // 实测「人因评估－gavriel salvendy…」和「gavriel salvendy…」出来是两块同样的品红，
  // 而书脊存在的全部理由就是让人一眼把它们分开。
  hash ^= hash >>> 16;
  hash = Math.imul(hash, 2246822507) >>> 0;
  hash ^= hash >>> 13;
  hash = Math.imul(hash, 3266489909) >>> 0;
  // `>>> 0` 不能省：`^=` 的结果是有符号 32 位数，可能为负，负数取模会索引到数组外面，
  // 拿回一个 undefined 颜色——React 见到 undefined 会把整个 style 属性丢掉，
  // 于是六个书脊一起变成透明。丢的不是颜色，是这一整个功能。
  hash = (hash ^ (hash >>> 16)) >>> 0;
  // 落到固定的色格上，而不是 360 度里随便取一个。
  //
  // 连续取色时，六本书实测挤成 162°/166° 和 304°/311°/314°/325° 两簇——差三度的两块颜色
  // 不像「两本不同的书」，像同一个颜色渲染坏了。分格之后，两本书要么明显不同色，
  // 要么就是同一个色；后者是可以接受的（书脊上还压着不同的字），前者才是要避免的。
  const HUES = [8, 32, 46, 88, 132, 168, 196, 214, 250, 278, 312, 338];
  const hue = HUES[hash % HUES.length];
  // 再分两档明度，把可分辨的组合从 12 个抬到 24 个。
  const dark = (hash >>> 8) % 2 === 0;
  return `hsl(${hue} ${dark ? 44 : 34}% ${dark ? 38 : 50}%)`;
}

/** 压在书脊上的那个字。中文取第一个字，英文取首字母；书名以标点开头时跳过它——
 *  《余罪》的书脊上应该是「余」，不是「《」。 */
function spineGlyph(title: string): string {
  const cleaned = (title || "").replace(/^[\s《「『（([【"'`~!@#$%^&*\-—_=+.,:;?]+/, "");
  const ch = (cleaned || title || "?").trim().charAt(0);
  return /[a-z]/i.test(ch) ? ch.toUpperCase() : ch || "?";
}

function deleteErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "BOOK_HAS_ACTIVE_TASKS") {
      return "这本书还有正在运行的分析任务，请先停止任务后再删除。";
    }
    if (error.code === "BOOK_NOT_FOUND" || error.status === 404) {
      return "这本书已经被删除或不存在。";
    }
    return error.message || "删除失败，书籍和分析数据均未发生变化。";
  }
  return "删除失败，书籍和分析数据均未发生变化。";
}

function BookRow({
  book,
  info,
  onDeleted,
  selected,
  onSelectedChange,
}: {
  book: Book;
  /** 后端算好的类型与分析状态。取不到时行会退回只显示格式与日期。 */
  info?: LibraryItem;
  onDeleted: (book: Book) => void;
  /** 勾中的书会一次性加进书单——一本一本加，十五本要点十五次。 */
  selected: boolean;
  onSelectedChange: (next: boolean) => void;
}) {
  const fmt = fileFormat(book.source_file_name);
  const moreTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deletingRef = useRef(false);
  const remove = useMutation({
    mutationFn: () => booksApi.delete(book.id),
    onSuccess: () => {
      setConfirmOpen(false);
      setDeleteError(null);
      onDeleted(book);
    },
    onError: (error) => {
      setDeleteError(deleteErrorMessage(error));
    },
    onSettled: () => {
      deletingRef.current = false;
    },
  });

  useEffect(() => {
    if (!confirmOpen) return;
    const id = window.setTimeout(() => {
      document
        .querySelector<HTMLButtonElement>(`[data-testid="book-delete-cancel-${book.id}"]`)
        ?.focus();
    }, 0);
    return () => window.clearTimeout(id);
  }, [confirmOpen, book.id]);

  const closeConfirm = () => {
    if (remove.isPending || deletingRef.current) return;
    setConfirmOpen(false);
    setDeleteError(null);
    window.setTimeout(() => moreTriggerRef.current?.focus(), 0);
  };

  const confirmDelete = () => {
    if (remove.isPending || deletingRef.current) return;
    deletingRef.current = true;
    remove.mutate();
  };

  return (
    <div
      className="book-row"
      data-testid={`book-row-${book.id}`}
      data-selected={selected ? "1" : undefined}
    >
      <label className="book-row-pick" title="选中，用于加入书单">
        <input
          type="checkbox"
          checked={selected}
          aria-label={`选择《${book.title}》`}
          data-testid={`book-pick-${book.id}`}
          onChange={(e) => onSelectedChange(e.target.checked)}
        />
      </label>
      <span
        className="book-spine"
        aria-hidden="true"
        style={{ background: spineColor(book.title) }}
      >
        {spineGlyph(book.title)}
      </span>
      <span className="book-row-main">
        {/* 整行可点。原来这里只有右边一个「打开」按钮，等于告诉用户
            「这一行的其他地方是死的」。 */}
        <Link className="book-row-title" to={`/books/${book.id}`} title={book.title}>
          {book.title}
        </Link>
        {/* 文件名只在和书名不同的时候才出现——同名时重复一遍是同一句话说两次。 */}
        {info?.source_file_name ? (
          <small className="book-row-filename" title={info.source_file_name}>
            {info.source_file_name}
          </small>
        ) : null}
        <small className="book-row-meta">
          {info ? (
            <>
              <span className={`book-kind book-kind--${info.material_kind}`}>
                {info.kind_label}
                {info.material_kind_confirmed ? "" : " · 待确认"}
              </span>
              {info.chapter_count > 0 ? `${info.chapter_count} 章 · ` : ""}
              <span className={`book-state book-state--${info.analysis_state}`}>
                {info.analysis_state_label}
              </span>
            </>
          ) : (
            <>
              {fmt !== "OTHER" ? `${fmt} · ` : ""}
              导入于 {new Date(book.created_at).toLocaleDateString()}
            </>
          )}
        </small>
      </span>
      <div className="book-row-actions">
        {/* 「打开」按钮去掉了——书名本身就是那个链接。这个隐藏的链接留给验收脚本和
            键盘用户：它们都按 book-open-<id> 找入口，拿掉会把「少一个按钮」变成
            「这一行没有可聚焦的出口」。 */}
        <Link
          className="book-row-open-sr"
          to={`/books/${book.id}`}
          data-testid={`book-open-${book.id}`}
          tabIndex={-1}
          aria-hidden="true"
        >
          打开
        </Link>
        <div className="book-row-more" ref={(node) => {
          const trigger = node?.querySelector<HTMLButtonElement>(".overflow-menu-trigger");
          moreTriggerRef.current = trigger || null;
        }}>
          <OverflowMenu
            label="⋯"
            data-testid={`book-more-${book.id}`}
            items={[
              {
                id: "delete",
                label: "删除书籍",
                danger: true,
                testId: `book-delete-${book.id}`,
                onSelect: () => {
                  setDeleteError(null);
                  setConfirmOpen(true);
                },
              },
            ]}
          />
        </div>
      </div>

      <Dialog
        open={confirmOpen}
        onClose={closeConfirm}
        title={`删除《${book.title}》？`}
        data-testid={`book-delete-dialog-${book.id}`}
        className="book-delete-dialog"
        footer={
          <>
            <Button
              variant="secondary"
              disabled={remove.isPending}
              onClick={closeConfirm}
              data-testid={`book-delete-cancel-${book.id}`}
              autoFocus
            >
              取消
            </Button>
            {remove.error instanceof ApiError &&
            remove.error.code === "BOOK_HAS_ACTIVE_TASKS" ? (
              <Link
                className="sl-btn sl-btn--secondary secondary"
                to="/tasks"
                data-testid={`book-delete-goto-tasks-${book.id}`}
              >
                前往任务中心
              </Link>
            ) : null}
            <Button
              variant="danger"
              loading={remove.isPending}
              disabled={remove.isPending}
              onClick={confirmDelete}
              data-testid={`book-delete-confirm-${book.id}`}
              aria-label={`确认删除《${book.title}》`}
            >
              {remove.isPending ? "正在删除…" : "确认删除"}
            </Button>
          </>
        }
      >
        <p data-testid={`book-delete-warning-${book.id}`}>
          此操作将从 StoryLens 中永久删除这本书及其章节、场景和分析结果，删除后无法恢复。
        </p>
        <p className="muted" data-testid={`book-delete-original-note-${book.id}`}>
          不会删除你电脑中的原始 TXT、DOCX 或 EPUB 文件。
        </p>
        {deleteError ? (
          <p className="danger" role="alert" data-testid={`book-delete-error-${book.id}`}>
            {deleteError}
          </p>
        ) : null}
      </Dialog>
    </div>
  );
}
