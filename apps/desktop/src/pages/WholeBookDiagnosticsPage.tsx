import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ErrorState, Loading } from "../components/common/States";
import { booksApi } from "../services/booksApi";
import { ApiError } from "../services/apiClient";
import { isWholeBookDiagnosticsEnabled } from "../services/wholeBookDiagnosticsFlag";
import { buildFoundationStageList } from "../services/wholeBookFoundationStages";
import {
  newFoundationClientRequestId,
  wholeBookFoundationApi,
  type BookSnapshotMetadata,
  type GenerateWindowsResponse,
  type SnapshotParagraphRow,
  type WholeBookRunRecord,
  type WholeBookRunStageRow,
  type WholeBookWindowCoverage,
  type WholeBookWindowRow,
} from "../services/wholeBookFoundationApi";
import type { Book } from "../types";
import styles from "./WholeBookDiagnosticsPage.module.css";

const PAGE_TITLE = "全书分析开发诊断页";
const PAGE_NOTICE = "当前仅验证 Snapshot、Run 和跨章窗口，不会调用大模型。";
const MODE_LABEL = "原生全书分析";
const ORIGIN_LABEL = "fixture";

function previewText(text: string, max = 120): string {
  const trimmed = text.trim();
  if (trimmed.length <= max) return trimmed;
  return `${trimmed.slice(0, max)}…`;
}

function formatRatio(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 1000) / 10}%`;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "请求失败";
}

type BookSummary = {
  book: Book;
  chapterCount: number | null;
  characterCount: number | null;
  bookRevisionHash: string | null;
};

function DiagnosticsUnavailable() {
  return (
    <section
      className={styles.wholeBookDiagnosticsUnavailable}
      data-testid="whole-book-diagnostics-unavailable"
    >
      <h1>{PAGE_TITLE}</h1>
      <p>该开发诊断页未启用。请设置环境变量 VITE_WHOLE_BOOK_DIAGNOSTICS_ENABLED=true 后重试。</p>
      <p className="muted">
        <Link to="/library">返回书库</Link>
      </p>
    </section>
  );
}

export function WholeBookDiagnosticsPage() {
  if (!isWholeBookDiagnosticsEnabled()) {
    return <DiagnosticsUnavailable />;
  }
  return <WholeBookDiagnosticsPageEnabled />;
}

function WholeBookDiagnosticsPageEnabled() {
  const [selectedBookId, setSelectedBookId] = useState<number | null>(null);
  const [snapshot, setSnapshot] = useState<BookSnapshotMetadata | null>(null);
  const [snapshotReused, setSnapshotReused] = useState<boolean | null>(null);
  const [clientRequestId, setClientRequestId] = useState(() => newFoundationClientRequestId());
  const [run, setRun] = useState<WholeBookRunRecord | null>(null);
  const [stages, setStages] = useState<WholeBookRunStageRow[]>([]);
  const [windowsResult, setWindowsResult] = useState<GenerateWindowsResponse | null>(null);
  const [coverage, setCoverage] = useState<WholeBookWindowCoverage | null>(null);
  const [selectedWindowId, setSelectedWindowId] = useState<number | null>(null);
  const [windowParagraphs, setWindowParagraphs] = useState<SnapshotParagraphRow[]>([]);
  const [showChapters, setShowChapters] = useState(false);
  const [showParagraphs, setShowParagraphs] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const booksQuery = useQuery({
    queryKey: ["whole-book-diagnostics-books"],
    queryFn: () => booksApi.list(),
  });

  const bookSummariesQuery = useQuery({
    queryKey: ["whole-book-diagnostics-book-summaries", booksQuery.data?.map((b) => b.id)],
    enabled: Boolean(booksQuery.data?.length),
    queryFn: async (): Promise<BookSummary[]> => {
      const books = booksQuery.data || [];
      const summaries = await Promise.all(
        books.map(async (book) => {
          let chapterCount: number | null = null;
          let characterCount: number | null = null;
          let bookRevisionHash: string | null = null;
          try {
            const chapters = await booksApi.chapters(book.id);
            chapterCount = chapters.length;
            characterCount = chapters.reduce((sum, ch) => sum + (ch.word_count || 0), 0);
          } catch {
            /* optional metadata */
          }
          try {
            const snaps = await wholeBookFoundationApi.listSnapshots(book.id);
            const latest = snaps.snapshots[0];
            if (latest) {
              bookRevisionHash = latest.content_hash;
              if (latest.character_count > 0) characterCount = latest.character_count;
              if (latest.chapter_count > 0) chapterCount = latest.chapter_count;
            }
          } catch {
            /* hash available after first snapshot */
          }
          return { book, chapterCount, characterCount, bookRevisionHash };
        }),
      );
      return summaries;
    },
  });

  const selectedSummary = useMemo(
    () => bookSummariesQuery.data?.find((row) => row.book.id === selectedBookId) ?? null,
    [bookSummariesQuery.data, selectedBookId],
  );

  const windows = windowsResult?.windows ?? [];
  const selectedWindow = windows.find((w) => w.window_id === selectedWindowId) ?? null;

  const stageList = useMemo(
    () => buildFoundationStageList(stages, run?.current_stage_code, run?.status),
    [stages, run?.current_stage_code, run?.status],
  );

  const refreshRun = useCallback(async (runId: number) => {
    const [runResp, stageResp] = await Promise.all([
      wholeBookFoundationApi.getRun(runId),
      wholeBookFoundationApi.listStages(runId),
    ]);
    setRun(runResp.run);
    setStages(stageResp.stages);
  }, []);

  const loadWindowDetail = useCallback(
    async (window: WholeBookWindowRow) => {
      if (!snapshot) return;
      setSelectedWindowId(window.window_id);
      const resp = await wholeBookFoundationApi.listSnapshotParagraphs(snapshot.snapshot_id, {
        offset: 0,
        limit: 500,
      });
      const filtered = resp.paragraphs.filter(
        (p) =>
          p.global_paragraph_index >= window.first_global_paragraph_index &&
          p.global_paragraph_index <= window.last_global_paragraph_index,
      );
      setWindowParagraphs(filtered);
    },
    [snapshot],
  );

  useEffect(() => {
    if (!selectedWindow) {
      setWindowParagraphs([]);
    }
  }, [selectedWindow]);

  async function withBusy<T>(label: string, action: () => Promise<T>): Promise<T | undefined> {
    setBusy(label);
    setError(null);
    try {
      return await action();
    } catch (err) {
      setError(errorMessage(err));
      return undefined;
    } finally {
      setBusy(null);
    }
  }

  async function handleCreateSnapshot() {
    if (!selectedBookId) return;
    await withBusy("snapshot", async () => {
      const resp = await wholeBookFoundationApi.createSnapshot(selectedBookId);
      setSnapshot(resp.snapshot);
      setSnapshotReused(resp.reused);
      setRun(null);
      setStages([]);
      setWindowsResult(null);
      setCoverage(null);
      setSelectedWindowId(null);
      await bookSummariesQuery.refetch();
    });
  }

  async function handleCreateRun() {
    if (!selectedBookId || !snapshot) return;
    const nextClientRequestId = newFoundationClientRequestId();
    setClientRequestId(nextClientRequestId);
    await withBusy("create-run", async () => {
      const resp = await wholeBookFoundationApi.createRun(selectedBookId, {
        snapshot_id: snapshot.snapshot_id,
        mode: "whole_book_native",
        client_request_id: nextClientRequestId,
        result_origin: "fixture",
      });
      setRun(resp.run);
      const stageResp = await wholeBookFoundationApi.listStages(resp.run.run_id);
      setStages(stageResp.stages);
      setWindowsResult(null);
      setCoverage(null);
    });
  }

  async function handleRunAction(action: "start" | "pause" | "resume" | "cancel") {
    if (!run) return;
    await withBusy(action, async () => {
      const apiCall =
        action === "start"
          ? wholeBookFoundationApi.startRun
          : action === "pause"
            ? wholeBookFoundationApi.pauseRun
            : action === "resume"
              ? wholeBookFoundationApi.resumeRun
              : wholeBookFoundationApi.cancelRun;
      const resp = await apiCall(run.run_id);
      setRun(resp.run);
      await refreshRun(run.run_id);
    });
  }

  async function handleGenerateWindows() {
    if (!run) return;
    await withBusy("windows", async () => {
      const resp = await wholeBookFoundationApi.generateWindows(run.run_id);
      setWindowsResult(resp);
      setCoverage(resp.coverage);
      await refreshRun(run.run_id);
    });
  }

  const canStart = run?.status === "pending";
  const canPause = run?.status === "running";
  const canResume = run?.status === "paused" || run?.status === "recoverable";
  const canCancel =
    run != null && !["completed", "failed", "cancelled"].includes(run.status);

  if (booksQuery.isLoading) return <Loading />;

  if (booksQuery.isError) {
    return (
      <ErrorState
        error={
          booksQuery.error instanceof Error
            ? booksQuery.error
            : new Error(errorMessage(booksQuery.error))
        }
        retry={() => void booksQuery.refetch()}
      />
    );
  }

  return (
    <section className={styles.wholeBookDiagnosticsPage} data-testid="whole-book-diagnostics-page">
      <header>
        <h1>{PAGE_TITLE}</h1>
        <div className={styles.wholeBookDiagnosticsBanner} data-testid="whole-book-diagnostics-banner">
          <p>{PAGE_NOTICE}</p>
          <p className="muted" data-testid="whole-book-diagnostics-provider-calls">
            Provider 调用次数：0（本页不触发模型调用）
          </p>
        </div>
      </header>

      {error ? (
        <p className="error-text" data-testid="whole-book-diagnostics-error">
          {error}
        </p>
      ) : null}

      <section className={styles.wholeBookDiagnosticsSection} data-testid="whole-book-diagnostics-book-select">
        <h2>1. 选择书籍</h2>
        <label>
          <span className="muted">书籍</span>
          <select
            value={selectedBookId ?? ""}
            onChange={(e) => {
              const id = Number(e.target.value);
              setSelectedBookId(Number.isFinite(id) && id > 0 ? id : null);
              setSnapshot(null);
              setSnapshotReused(null);
              setRun(null);
              setStages([]);
              setWindowsResult(null);
              setCoverage(null);
            }}
          >
            <option value="">— 选择 —</option>
            {(booksQuery.data || []).map((book) => (
              <option key={book.id} value={book.id}>
                {book.title}
              </option>
            ))}
          </select>
        </label>
        {selectedSummary ? (
          <dl className={styles.wholeBookDiagnosticsMeta}>
            <div>
              <dt>章节数</dt>
              <dd>{selectedSummary.chapterCount ?? "—"}</dd>
            </div>
            <div>
              <dt>字符数</dt>
              <dd>{selectedSummary.characterCount ?? "—"}</dd>
            </div>
            <div>
              <dt>book_revision_hash</dt>
              <dd data-testid="whole-book-diagnostics-revision-hash">
                {selectedSummary.bookRevisionHash ?? snapshot?.content_hash ?? "（创建 Snapshot 后可用）"}
              </dd>
            </div>
          </dl>
        ) : null}
        <div className={styles.wholeBookDiagnosticsActions}>
          <button
            type="button"
            disabled={!selectedBookId || busy != null}
            data-testid="whole-book-diagnostics-create-snapshot"
            onClick={() => void handleCreateSnapshot()}
          >
            {busy === "snapshot" ? "处理中…" : "创建/复用 Snapshot"}
          </button>
        </div>
      </section>

      {snapshot ? (
        <section className={styles.wholeBookDiagnosticsSection} data-testid="whole-book-diagnostics-snapshot">
          <h2>2. Snapshot</h2>
          {snapshotReused ? (
            <span className={styles.wholeBookDiagnosticsBadge} data-testid="whole-book-diagnostics-snapshot-reused">
              已复用
            </span>
          ) : null}
          <dl className={styles.wholeBookDiagnosticsMeta}>
            {(
              [
                ["snapshot_id", snapshot.snapshot_id],
                ["snapshot_version", snapshot.snapshot_version],
                ["status", snapshot.status],
                ["content_hash", snapshot.content_hash],
                ["chapter_count", snapshot.chapter_count],
                ["paragraph_count", snapshot.paragraph_count],
                ["character_count", snapshot.character_count],
                ["created_at", snapshot.created_at],
                ["completed_at", snapshot.completed_at],
              ] as const
            ).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{value ?? "—"}</dd>
              </div>
            ))}
          </dl>
          <div className={styles.wholeBookDiagnosticsActions}>
            <button type="button" onClick={() => setShowChapters((v) => !v)}>
              {showChapters ? "隐藏章节" : "查看章节"}
            </button>
            <button type="button" onClick={() => setShowParagraphs((v) => !v)}>
              {showParagraphs ? "隐藏段落" : "查看前 20 段落"}
            </button>
          </div>
          {showChapters ? <SnapshotChaptersPanel snapshotId={snapshot.snapshot_id} /> : null}
          {showParagraphs ? (
            <SnapshotParagraphsPanel snapshotId={snapshot.snapshot_id} limit={20} />
          ) : null}
        </section>
      ) : null}

      {snapshot ? (
        <section className={styles.wholeBookDiagnosticsSection} data-testid="whole-book-diagnostics-run-create">
          <h2>3. 创建测试 Run</h2>
          <dl className={styles.wholeBookDiagnosticsMeta}>
            <div>
              <dt>mode</dt>
              <dd>{MODE_LABEL} (whole_book_native)</dd>
            </div>
            <div>
              <dt>result_origin</dt>
              <dd>{ORIGIN_LABEL}</dd>
            </div>
            <div>
              <dt>client_request_id</dt>
              <dd>{clientRequestId}</dd>
            </div>
          </dl>
          <div className={styles.wholeBookDiagnosticsActions}>
            <button
              type="button"
              disabled={!snapshot || snapshot.status !== "completed" || busy != null}
              data-testid="whole-book-diagnostics-create-run"
              onClick={() => void handleCreateRun()}
            >
              {busy === "create-run" ? "创建中…" : "创建测试 Run"}
            </button>
          </div>
        </section>
      ) : null}

      {run ? (
        <section className={styles.wholeBookDiagnosticsSection} data-testid="whole-book-diagnostics-run-panel">
          <h2>4. Run 状态</h2>
          <dl className={styles.wholeBookDiagnosticsMeta}>
            {(
              [
                ["run_id", run.run_id],
                ["snapshot_id", run.snapshot_id],
                ["mode", run.mode],
                ["status", run.status],
                ["current_stage_code", run.current_stage_code],
                ["contract_version", run.contract_version],
                ["engine_id", run.engine_id],
                ["client_request_id", clientRequestId],
              ] as const
            ).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{value ?? "—"}</dd>
              </div>
            ))}
          </dl>
          <div className={styles.wholeBookDiagnosticsActions}>
            <button
              type="button"
              disabled={!canStart || busy != null}
              data-testid="whole-book-diagnostics-run-start"
              onClick={() => void handleRunAction("start")}
            >
              开始
            </button>
            <button
              type="button"
              disabled={!canPause || busy != null}
              data-testid="whole-book-diagnostics-run-pause"
              onClick={() => void handleRunAction("pause")}
            >
              暂停
            </button>
            <button
              type="button"
              disabled={!canResume || busy != null}
              data-testid="whole-book-diagnostics-run-resume"
              onClick={() => void handleRunAction("resume")}
            >
              恢复
            </button>
            <button
              type="button"
              disabled={!canCancel || busy != null}
              data-testid="whole-book-diagnostics-run-cancel"
              onClick={() => void handleRunAction("cancel")}
            >
              取消
            </button>
          </div>
          <h3>Stages（7）</h3>
          <ul className={styles.wholeBookDiagnosticsStageList}>
            {stageList.map((item) => (
              <li
                key={item.key}
                data-state={item.state}
                data-testid={`whole-book-diagnostics-stage-item-${item.key}`}
              >
                {item.label} · {item.key} · {item.state}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {run ? (
        <section className={styles.wholeBookDiagnosticsSection} data-testid="whole-book-diagnostics-windows">
          <h2>5. 跨章窗口</h2>
          <div className={styles.wholeBookDiagnosticsActions}>
            <button
              type="button"
              disabled={busy != null}
              data-testid="whole-book-diagnostics-generate-windows"
              onClick={() => void handleGenerateWindows()}
            >
              {busy === "windows" ? "生成中…" : "生成/复用跨章窗口"}
            </button>
          </div>
          {coverage || windowsResult?.coverage ? (
            <CoverageCards
              coverage={coverage ?? windowsResult!.coverage}
              windowingVersion={windowsResult?.windowing_version ?? "whole_book_windowing_v1"}
              windowCount={windows.length}
            />
          ) : null}
          {windows.length ? (
            <table className={styles.wholeBookDiagnosticsTable} data-testid="whole-book-diagnostics-window-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>章节起止</th>
                  <th>first</th>
                  <th>core_start</th>
                  <th>last</th>
                  <th>段落数</th>
                  <th>tokens</th>
                  <th>overlap_before</th>
                  <th>window_hash</th>
                  <th>status</th>
                </tr>
              </thead>
              <tbody>
                {windows.map((window) => {
                  const coreStart =
                    window.first_global_paragraph_index + window.overlap_before_paragraphs;
                  return (
                  <tr
                    key={window.window_id}
                    data-selected={selectedWindowId === window.window_id ? "true" : "false"}
                    onClick={() => void loadWindowDetail(window)}
                    style={{ cursor: "pointer" }}
                  >
                    <td>{window.window_index}</td>
                    <td>
                      {window.chapter_start_index}–{window.chapter_end_index}
                    </td>
                    <td>{window.first_global_paragraph_index}</td>
                    <td>{coreStart}</td>
                    <td>{window.last_global_paragraph_index}</td>
                    <td>{window.paragraph_count}</td>
                    <td>{window.token_estimate}</td>
                    <td>{window.overlap_before_paragraphs}</td>
                    <td title={window.window_hash}>{window.window_hash.slice(0, 12)}…</td>
                    <td>{window.status}</td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <p className="muted">尚未生成窗口。</p>
          )}
          {selectedWindow ? (
            <WindowDetailPanel window={selectedWindow} paragraphs={windowParagraphs} />
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

function CoverageCards({
  coverage,
  windowingVersion,
  windowCount,
}: {
  coverage: WholeBookWindowCoverage;
  windowingVersion: string;
  windowCount: number;
}) {
  const coverageOk =
    coverage.coverage_ratio === 1 &&
    coverage.uncovered_paragraphs === 0 &&
    coverage.order_valid;
  const cards = [
    ["窗口数量", windowCount],
    ["总段落", coverage.total_paragraphs],
    ["唯一覆盖", coverage.covered_unique_paragraphs],
    ["重复计数", coverage.duplicated_paragraphs],
    ["遗漏", coverage.uncovered_paragraphs],
    ["覆盖率", formatRatio(coverage.coverage_ratio)],
    ["顺序有效", coverage.order_valid ? "是" : "否"],
    ["算法版本", windowingVersion],
  ] as const;
  return (
    <div className={styles.wholeBookDiagnosticsCoverageCards} data-testid="whole-book-diagnostics-coverage">
      {!coverageOk ? (
        <p className="error-text" data-testid="whole-book-diagnostics-coverage-alert">
          覆盖异常：覆盖率未达 100%、存在遗漏段落，或顺序无效。
        </p>
      ) : null}
      {cards.map(([label, value]) => (
        <div key={label} className={styles.wholeBookDiagnosticsCoverageCard}>
          <span className="muted">{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function SnapshotChaptersPanel({ snapshotId }: { snapshotId: number }) {
  const query = useQuery({
    queryKey: ["whole-book-diagnostics-snapshot-chapters", snapshotId],
    queryFn: () => wholeBookFoundationApi.listSnapshotChapters(snapshotId),
  });
  if (query.isLoading) return <p className="muted">加载章节…</p>;
  if (query.isError) return <p className="error-text">{errorMessage(query.error)}</p>;
  return (
    <ul>
      {(query.data?.chapters || []).map((ch) => (
        <li key={ch.snapshot_chapter_id}>
          [{ch.chapter_index}] {ch.title || "无标题"} · {ch.paragraph_count} 段
        </li>
      ))}
    </ul>
  );
}

function SnapshotParagraphsPanel({ snapshotId, limit }: { snapshotId: number; limit: number }) {
  const query = useQuery({
    queryKey: ["whole-book-diagnostics-snapshot-paragraphs", snapshotId, limit],
    queryFn: () =>
      wholeBookFoundationApi.listSnapshotParagraphs(snapshotId, { offset: 0, limit }),
  });
  if (query.isLoading) return <p className="muted">加载段落…</p>;
  if (query.isError) return <p className="error-text">{errorMessage(query.error)}</p>;
  return (
    <ul>
      {(query.data?.paragraphs || []).map((p) => (
        <li key={p.snapshot_paragraph_id}>
          g{p.global_paragraph_index} · {previewText(p.text)}
        </li>
      ))}
    </ul>
  );
}

function WindowDetailPanel({
  window,
  paragraphs,
}: {
  window: WholeBookWindowRow;
  paragraphs: SnapshotParagraphRow[];
}) {
  const coreStart =
    window.overlap_before_paragraphs > 0
      ? window.first_global_paragraph_index + window.overlap_before_paragraphs
      : window.first_global_paragraph_index;

  return (
    <div className={styles.wholeBookDiagnosticsWindowDetail} data-testid="whole-book-diagnostics-window-detail">
      <h3>窗口 #{window.window_index}</h3>
      <dl className={styles.wholeBookDiagnosticsMeta}>
        <div>
          <dt>覆盖章节</dt>
          <dd>
            {window.chapter_start_index} – {window.chapter_end_index}
          </dd>
        </div>
        <div>
          <dt>first_global_paragraph_index</dt>
          <dd>{window.first_global_paragraph_index}</dd>
        </div>
        <div>
          <dt>core_start_global_paragraph_index</dt>
          <dd>{coreStart}</dd>
        </div>
        <div>
          <dt>last_global_paragraph_index</dt>
          <dd>{window.last_global_paragraph_index}</dd>
        </div>
        <div>
          <dt>overlap_before_paragraphs</dt>
          <dd>{window.overlap_before_paragraphs}</dd>
        </div>
        <div>
          <dt>window_hash</dt>
          <dd>{window.window_hash}</dd>
        </div>
      </dl>
      <ul>
        {paragraphs.map((p) => (
          <li key={p.snapshot_paragraph_id}>
            ch{p.chapter_index} p{p.paragraph_index} g{p.global_paragraph_index} ·{" "}
            <code>{p.text_hash.slice(0, 12)}…</code>
            <p className={styles.wholeBookDiagnosticsParagraphPreview}>{previewText(p.text, 120)}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
