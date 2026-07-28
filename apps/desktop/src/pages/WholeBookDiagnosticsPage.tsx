import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ErrorState, Loading } from "../components/common/States";
import { booksApi } from "../services/booksApi";
import { ApiError } from "../services/apiClient";
import { isWholeBookDiagnosticsEnabled } from "../services/wholeBookDiagnosticsFlag";
import { isWholeBookRealProviderEnabled } from "../services/wholeBookRealProviderFlag";
import { buildFoundationStageList } from "../services/wholeBookFoundationStages";
import {
  BOOK_OVERVIEW_CLAIM_LABELS,
  BOOK_OVERVIEW_CLAIM_ORDER,
  newFoundationClientRequestId,
  OTHER_ASSET_GROUPS,
  wholeBookFoundationApi,
  type BookOverviewClaimRow,
  type BookOverviewResultRow,
  type BookSnapshotMetadata,
  type EvidenceSourceDetail,
  type GenerateWindowsResponse,
  type MinimalAnalysisSummary,
  type NarrativeAssetRow,
  type NarrativeEntityRow,
  type NarrativeEvidenceRow,
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
const FIXTURE_PIPELINE_NOTICE =
  "当前按钮仅运行 Fixture，用于验证人物、事件、证据和总览持久化，不调用真实模型。";
const MODE_LABEL = "原生全书分析";
const ORIGIN_LABEL = "fixture";

function overviewAvailabilityLabel(availability: string): string {
  if (availability === "available") return "可用";
  if (availability === "insufficient_evidence") return "证据不足";
  if (availability === "unavailable") return "不可用";
  return availability;
}

function formatAliasNames(aliases: Array<{ name: string }>): string {
  if (!aliases.length) return "—";
  return aliases.map((a) => a.name).join("、");
}

function highlightQuoteInParagraph(
  paragraphText: string,
  quoteText: string,
  startOffset: number,
  endOffset: number,
): { before: string; quote: string; after: string } {
  if (
    startOffset >= 0 &&
    endOffset > startOffset &&
    endOffset <= paragraphText.length &&
    paragraphText.slice(startOffset, endOffset) === quoteText
  ) {
    return {
      before: paragraphText.slice(0, startOffset),
      quote: quoteText,
      after: paragraphText.slice(endOffset),
    };
  }
  const idx = paragraphText.indexOf(quoteText);
  if (idx >= 0) {
    return {
      before: paragraphText.slice(0, idx),
      quote: quoteText,
      after: paragraphText.slice(idx + quoteText.length),
    };
  }
  return { before: paragraphText, quote: "", after: "" };
}

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
  const [minimalSummary, setMinimalSummary] = useState<MinimalAnalysisSummary | null>(null);
  const [entities, setEntities] = useState<NarrativeEntityRow[]>([]);
  const [eventAssets, setEventAssets] = useState<NarrativeAssetRow[]>([]);
  const [otherAssetsByType, setOtherAssetsByType] = useState<Record<string, NarrativeAssetRow[]>>(
    {},
  );
  const [evidences, setEvidences] = useState<NarrativeEvidenceRow[]>([]);
  const [overview, setOverview] = useState<BookOverviewResultRow | null>(null);
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(null);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<number | null>(null);
  const [evidenceSource, setEvidenceSource] = useState<EvidenceSourceDetail | null>(null);
  const [expandedClaimKey, setExpandedClaimKey] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const realProviderEnabled = isWholeBookRealProviderEnabled();
  const providerRealCalls = minimalSummary?.provider_real_call_count ?? 0;
  const providerFixtureCalls = minimalSummary?.provider_fixture_call_count ?? 0;

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
  const selectedEntity = entities.find((e) => e.entity_id === selectedEntityId) ?? null;

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

  const loadMinimalAnalysisData = useCallback(async (runId: number) => {
    const [summaryResp, entitiesResp, eventResp, evidencesResp, overviewResp] = await Promise.all([
      wholeBookFoundationApi.getMinimalAnalysisSummary(runId),
      wholeBookFoundationApi.listEntities(runId),
      wholeBookFoundationApi.listAssets(runId, { asset_type: "event", limit: 200 }),
      wholeBookFoundationApi.listEvidences(runId),
      wholeBookFoundationApi.getOverview(runId),
    ]);
    setMinimalSummary(summaryResp.summary);
    setEntities(entitiesResp.entities);
    setEventAssets(eventResp.assets);
    setEvidences(evidencesResp.evidences);
    setOverview(overviewResp.overview);

    const otherGroups = await Promise.all(
      OTHER_ASSET_GROUPS.map(async (group) => {
        const resp = await wholeBookFoundationApi.listAssets(runId, {
          asset_type: group.asset_type,
          limit: 100,
        });
        return [group.asset_type, resp.assets] as const;
      }),
    );
    setOtherAssetsByType(Object.fromEntries(otherGroups));
    await refreshRun(runId);
  }, [refreshRun]);

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
      resetMinimalAnalysisState();
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
      resetMinimalAnalysisState();
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

  async function handleExecuteMinimalAnalysisFixture() {
    if (!run) return;
    await withBusy("minimal-fixture", async () => {
      const resp = await wholeBookFoundationApi.executeMinimalAnalysisFixture(run.run_id);
      setRun(resp.run);
      setMinimalSummary(resp.summary);
      await loadMinimalAnalysisData(run.run_id);
    });
  }

  async function handleSelectEvidence(evidenceId: number) {
    setSelectedEvidenceId(evidenceId);
    setEvidenceSource(null);
    await withBusy("evidence-source", async () => {
      const resp = await wholeBookFoundationApi.getEvidenceSource(evidenceId);
      setEvidenceSource(resp.source);
    });
  }

  function resetMinimalAnalysisState() {
    setMinimalSummary(null);
    setEntities([]);
    setEventAssets([]);
    setOtherAssetsByType({});
    setEvidences([]);
    setOverview(null);
    setSelectedEntityId(null);
    setSelectedEvidenceId(null);
    setEvidenceSource(null);
    setExpandedClaimKey(null);
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
          <p className="muted" data-testid="whole-book-diagnostics-fixture-result">
            Fixture Result：{run?.result_origin ?? ORIGIN_LABEL}
          </p>
          <p className="muted" data-testid="whole-book-diagnostics-provider-real-calls">
            Provider Real Calls = {providerRealCalls}
          </p>
          <p className="muted" data-testid="whole-book-diagnostics-provider-calls">
            Provider 调用次数：{providerFixtureCalls}（Fixture）；本页不触发真实模型调用
          </p>
          {realProviderEnabled ? (
            <p className="error-text" data-testid="whole-book-diagnostics-real-provider-flag">
              警告：VITE_WHOLE_BOOK_REAL_PROVIDER_ENABLED 已开启，但本页不提供真实 Provider 控件。
            </p>
          ) : null}
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
              resetMinimalAnalysisState();
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

      {run ? (
        <section
          className={styles.wholeBookDiagnosticsSection}
          data-testid="whole-book-diagnostics-minimal-pipeline"
        >
          <h2>6. 最小分析管线</h2>
          <p className={styles.wholeBookDiagnosticsNotice} data-testid="whole-book-diagnostics-fixture-notice">
            {FIXTURE_PIPELINE_NOTICE}
          </p>
          <div className={styles.wholeBookDiagnosticsActions}>
            <button
              type="button"
              disabled={busy != null}
              data-testid="whole-book-diagnostics-run-minimal-fixture"
              onClick={() => void handleExecuteMinimalAnalysisFixture()}
            >
              {busy === "minimal-fixture" ? "运行中…" : "运行 Fixture 最小分析"}
            </button>
          </div>
          {minimalSummary ? (
            <MinimalAnalysisProgress summary={minimalSummary} stageCode={run.current_stage_code} />
          ) : (
            <p className="muted">尚未运行 Fixture 最小分析。</p>
          )}
        </section>
      ) : null}

      {entities.length ? (
        <section
          className={styles.wholeBookDiagnosticsSection}
          data-testid="whole-book-diagnostics-characters"
        >
          <h2>7. 人物</h2>
          <table className={styles.wholeBookDiagnosticsTable} data-testid="whole-book-diagnostics-entity-table">
            <thead>
              <tr>
                <th>entity_id</th>
                <th>canonical_name</th>
                <th>aliases</th>
                <th>state</th>
                <th>confidence</th>
                <th>evidence_count</th>
                <th>event_count</th>
              </tr>
            </thead>
            <tbody>
              {entities.map((entity) => (
                <tr
                  key={entity.entity_id}
                  data-selected={selectedEntityId === entity.entity_id ? "true" : "false"}
                  onClick={() =>
                    setSelectedEntityId((prev) =>
                      prev === entity.entity_id ? null : entity.entity_id,
                    )
                  }
                  style={{ cursor: "pointer" }}
                >
                  <td>{entity.entity_id}</td>
                  <td>{entity.canonical_name}</td>
                  <td>{formatAliasNames(entity.aliases)}</td>
                  <td>{entity.state}</td>
                  <td>{entity.confidence}</td>
                  <td>{entity.evidence_count}</td>
                  <td>{entity.event_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {selectedEntity ? <EntityDetailPanel entity={selectedEntity} /> : null}
        </section>
      ) : null}

      {eventAssets.length ? (
        <section
          className={styles.wholeBookDiagnosticsSection}
          data-testid="whole-book-diagnostics-events"
        >
          <h2>8. 事件</h2>
          <table className={styles.wholeBookDiagnosticsTable} data-testid="whole-book-diagnostics-event-table">
            <thead>
              <tr>
                <th>asset_id</th>
                <th>title</th>
                <th>event_type</th>
                <th>chapters</th>
                <th>participants</th>
                <th>confidence</th>
                <th>evidence_count</th>
              </tr>
            </thead>
            <tbody>
              {eventAssets.map((asset) => (
                <tr key={asset.asset_id}>
                  <td>{asset.asset_id}</td>
                  <td>{asset.title}</td>
                  <td>{asset.event_type ?? "—"}</td>
                  <td>{asset.chapters?.join("、") ?? "—"}</td>
                  <td>{asset.participants?.join("、") ?? "—"}</td>
                  <td>{asset.confidence}</td>
                  <td>{asset.evidence_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {OTHER_ASSET_GROUPS.some((g) => (otherAssetsByType[g.asset_type] ?? []).length > 0) ? (
        <section
          className={styles.wholeBookDiagnosticsSection}
          data-testid="whole-book-diagnostics-other-assets"
        >
          <h2>9. 其他资产</h2>
          {OTHER_ASSET_GROUPS.map((group) => {
            const rows = otherAssetsByType[group.asset_type] ?? [];
            if (!rows.length) return null;
            return (
              <div key={group.asset_type} className={styles.wholeBookDiagnosticsAssetGroup}>
                <h3>{group.label}</h3>
                <ul>
                  {rows.map((asset) => (
                    <li key={asset.asset_id}>
                      [{asset.asset_id}] {asset.title}
                      {asset.summary ? ` · ${previewText(asset.summary, 80)}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </section>
      ) : null}

      {evidences.length ? (
        <section
          className={styles.wholeBookDiagnosticsSection}
          data-testid="whole-book-diagnostics-evidences"
        >
          <h2>10. Evidence detail</h2>
          <table className={styles.wholeBookDiagnosticsTable} data-testid="whole-book-diagnostics-evidence-table">
            <thead>
              <tr>
                <th>evidence_id</th>
                <th>state</th>
                <th>confidence</th>
                <th>chapter</th>
                <th>paragraph</th>
                <th>global</th>
                <th>quote</th>
              </tr>
            </thead>
            <tbody>
              {evidences.map((ev) => (
                <tr
                  key={ev.evidence_id}
                  data-selected={selectedEvidenceId === ev.evidence_id ? "true" : "false"}
                  onClick={() => void handleSelectEvidence(ev.evidence_id)}
                  style={{ cursor: "pointer" }}
                >
                  <td>{ev.evidence_id}</td>
                  <td>{ev.state}</td>
                  <td>{ev.confidence}</td>
                  <td>{ev.chapter_index ?? "—"}</td>
                  <td>{ev.paragraph_index ?? "—"}</td>
                  <td>{ev.global_paragraph_index ?? "—"}</td>
                  <td>{ev.quote_text ? previewText(ev.quote_text, 40) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {evidenceSource ? (
            <EvidenceSourcePanel source={evidenceSource} busy={busy === "evidence-source"} />
          ) : null}
        </section>
      ) : null}

      {overview ? (
        <section
          className={styles.wholeBookDiagnosticsSection}
          data-testid="whole-book-diagnostics-overview"
        >
          <h2>11. 全书总览</h2>
          <OverviewClaimsPanel
            overview={overview}
            expandedClaimKey={expandedClaimKey}
            onToggleClaim={(key) =>
              setExpandedClaimKey((prev) => (prev === key ? null : key))
            }
            evidences={evidences}
            assets={[...eventAssets, ...Object.values(otherAssetsByType).flat()]}
          />
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

function MinimalAnalysisProgress({
  summary,
  stageCode,
}: {
  summary: MinimalAnalysisSummary;
  stageCode: string | null;
}) {
  return (
    <dl
      className={styles.wholeBookDiagnosticsMeta}
      data-testid="whole-book-diagnostics-minimal-progress"
    >
      <div>
        <dt>current_stage</dt>
        <dd>{stageCode ?? summary.current_stage_code ?? "—"}</dd>
      </div>
      <div>
        <dt>completed_windows / total</dt>
        <dd>
          {summary.completed_windows} / {summary.total_windows}
        </dd>
      </div>
      <div>
        <dt>entity_count</dt>
        <dd>{summary.entity_count}</dd>
      </div>
      <div>
        <dt>asset_count</dt>
        <dd>{summary.asset_count}</dd>
      </div>
      <div>
        <dt>evidence_count</dt>
        <dd>{summary.evidence_count}</dd>
      </div>
      <div>
        <dt>provider_fixture_call_count</dt>
        <dd>{summary.provider_fixture_call_count}</dd>
      </div>
    </dl>
  );
}

function EntityDetailPanel({ entity }: { entity: NarrativeEntityRow }) {
  return (
    <div className={styles.wholeBookDiagnosticsDetailPanel} data-testid="whole-book-diagnostics-entity-detail">
      <h3>{entity.canonical_name}</h3>
      <dl className={styles.wholeBookDiagnosticsMeta}>
        <div>
          <dt>aliases</dt>
          <dd>{formatAliasNames(entity.aliases)}</dd>
        </div>
      </dl>
      {entity.character_profile ? (
        <div>
          <h4>character_profile</h4>
          <p>{entity.character_profile.title}</p>
          {entity.character_profile.summary ? (
            <p className="muted">{entity.character_profile.summary}</p>
          ) : null}
        </div>
      ) : null}
      {entity.goals?.length ? (
        <div>
          <h4>goals</h4>
          <ul>
            {entity.goals.map((g) => (
              <li key={g.asset_id}>
                [{g.asset_id}] {g.title}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {entity.events?.length ? (
        <div>
          <h4>events</h4>
          <ul>
            {entity.events.map((ev) => (
              <li key={ev.asset_id}>
                [{ev.asset_id}] {ev.title}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {entity.linked_evidences?.length ? (
        <div>
          <h4>evidences</h4>
          <ul>
            {entity.linked_evidences.map((ev) => (
              <li key={ev.evidence_id}>
                #{ev.evidence_id} · {ev.quote_text ? previewText(ev.quote_text, 60) : "—"}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function EvidenceSourcePanel({
  source,
  busy,
}: {
  source: EvidenceSourceDetail;
  busy: boolean;
}) {
  const parts = highlightQuoteInParagraph(
    source.paragraph_text,
    source.quote_text,
    source.start_offset,
    source.end_offset,
  );
  return (
    <div className={styles.wholeBookDiagnosticsDetailPanel} data-testid="whole-book-diagnostics-evidence-detail">
      <h3>Evidence #{source.evidence_id}</h3>
      <dl className={styles.wholeBookDiagnosticsMeta}>
        <div>
          <dt>chapter</dt>
          <dd>
            [{source.chapter_index}] {source.chapter_title}
          </dd>
        </div>
        <div>
          <dt>paragraph_index</dt>
          <dd>{source.paragraph_index}</dd>
        </div>
        <div>
          <dt>global_paragraph_index</dt>
          <dd>{source.global_paragraph_index}</dd>
        </div>
        <div>
          <dt>hash state</dt>
          <dd>{source.state}</dd>
        </div>
      </dl>
      {busy ? <p className="muted">加载段落…</p> : null}
      <p className={styles.wholeBookDiagnosticsParagraphFull} data-testid="whole-book-diagnostics-evidence-paragraph">
        {parts.before}
        {parts.quote ? (
          <mark className={styles.wholeBookDiagnosticsQuoteHighlight}>{parts.quote}</mark>
        ) : null}
        {parts.after}
      </p>
    </div>
  );
}

function OverviewClaimsPanel({
  overview,
  expandedClaimKey,
  onToggleClaim,
  evidences,
  assets,
}: {
  overview: BookOverviewResultRow;
  expandedClaimKey: string | null;
  onToggleClaim: (key: string) => void;
  evidences: NarrativeEvidenceRow[];
  assets: NarrativeAssetRow[];
}) {
  const claimByKey = new Map(overview.claims.map((c) => [c.claim_key, c]));
  const evidenceById = new Map(evidences.map((e) => [e.evidence_id, e]));
  const assetById = new Map(assets.map((a) => [a.asset_id, a]));

  return (
    <ul className={styles.wholeBookDiagnosticsClaimList} data-testid="whole-book-diagnostics-claim-list">
      {BOOK_OVERVIEW_CLAIM_ORDER.map((claimKey) => {
        const claim = claimByKey.get(claimKey);
        const label = BOOK_OVERVIEW_CLAIM_LABELS[claimKey] ?? claimKey;
        const expanded = expandedClaimKey === claimKey;
        return (
          <li
            key={claimKey}
            data-testid={`whole-book-diagnostics-claim-${claimKey}`}
            data-availability={claim?.availability ?? "unavailable"}
          >
            <button
              type="button"
              className={styles.wholeBookDiagnosticsClaimButton}
              onClick={() => onToggleClaim(claimKey)}
            >
              <strong>{label}</strong>
              <span className="muted">
                {overviewAvailabilityLabel(claim?.availability ?? "unavailable")}
                {claim?.confidence != null ? ` · 置信度 ${claim.confidence}` : ""}
                {claim ? ` · 证据 ${claim.evidence_ids.length} · 资产 ${claim.supporting_asset_ids.length}` : ""}
              </span>
            </button>
            {claim?.availability === "insufficient_evidence" ? (
              <p className={styles.wholeBookDiagnosticsInsufficient} data-testid="whole-book-diagnostics-insufficient-evidence">
                证据不足：{claim.summary ?? "暂无足够证据支撑该结论。"}
              </p>
            ) : null}
            {claim?.summary && claim.availability !== "insufficient_evidence" ? (
              <p>{claim.summary}</p>
            ) : null}
            {expanded && claim ? (
              <OverviewClaimExpansion
                claim={claim}
                evidenceById={evidenceById}
                assetById={assetById}
              />
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function OverviewClaimExpansion({
  claim,
  evidenceById,
  assetById,
}: {
  claim: BookOverviewClaimRow;
  evidenceById: Map<number, NarrativeEvidenceRow>;
  assetById: Map<number, NarrativeAssetRow>;
}) {
  return (
    <div className={styles.wholeBookDiagnosticsClaimExpansion}>
      {claim.evidence_ids.length ? (
        <div>
          <h4>evidences</h4>
          <ul>
            {claim.evidence_ids.map((id) => {
              const ev = evidenceById.get(id);
              return (
                <li key={id}>
                  #{id}
                  {ev?.quote_text ? ` · ${previewText(ev.quote_text, 50)}` : ""}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
      {claim.supporting_asset_ids.length ? (
        <div>
          <h4>assets</h4>
          <ul>
            {claim.supporting_asset_ids.map((id) => {
              const asset = assetById.get(id);
              return (
                <li key={id}>
                  [{id}] {asset?.title ?? "—"}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
