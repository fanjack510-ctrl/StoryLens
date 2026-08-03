import { useEffect, useMemo, useState } from "react";
import type {
  ChapterFunctionItemV2,
  ChapterFunctionsClientViewState,
  ChapterFunctionsProductResponse,
  CanonicalFunctionLabel,
} from "../../../services/chapterFunctionsResultV2";
import {
  CANONICAL_FUNCTION_LABELS,
  CHAPTER_FUNCTIONS_CONTRACT_PACKAGE_VERSION,
  FUNCTION_LABEL_SEMANTICS_ZH,
  firstEvidenceIdForChapter,
  functionLabelDisplayZh,
  isCanonicalFunctionLabel,
} from "../../../services/chapterFunctionsResultV2";
import styles from "./ChapterFunctionsPanel.module.css";

const INSUFFICIENT_MESSAGE =
  "当前原文覆盖或证据不足，暂无法可靠识别章节功能。";
const PRIMARY_NULL_MESSAGE = "未识别出足够可靠的主要功能";
const SECONDARY_EMPTY_MESSAGE = "未识别出明确的辅助功能";

export type ChapterFunctionsFilters = {
  function: string;
  status: string;
};

const CLAIM_STATUS_OPTIONS = [
  { value: "", label: "全部状态" },
  { value: "observed", label: "观察（observed）" },
  { value: "inferred", label: "推断（inferred）" },
  { value: "not_observed", label: "未观察（not_observed）" },
] as const;

function formatConfidence(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return String(Math.round(value * 1000) / 1000);
}

function snippet(text: string | null | undefined, max = 72): string {
  if (!text) return "—";
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function chapterKey(item: ChapterFunctionItemV2): string {
  return String(item.chapter_id);
}

function wb21ContextLabel(caps: Record<string, unknown> | null | undefined): string {
  if (!caps) return "未提供（可选，非硬依赖）";
  const status = String(caps.structure_context_status ?? "");
  const used = caps.structure_context_used === true;
  if (status === "available" || used) return "已使用故事结构派生上下文（可选）";
  if (status === "insufficient") return "故事结构上下文不足（可选；不阻碍本章节功能）";
  if (status === "absent" || status === "failed" || status === "canceled") {
    return "未使用故事结构上下文（可选；非硬依赖）";
  }
  if (used === false) return "未使用故事结构上下文（可选）";
  return "未提供（可选，非硬依赖）";
}

function PrimaryLabel({ wire }: { wire: string | null }) {
  if (wire == null) {
    return <span data-testid="cf-primary-null">{PRIMARY_NULL_MESSAGE}</span>;
  }
  return (
    <span className={`${styles.tag} ${styles.tagPrimary}`} data-testid="cf-primary-label" data-wire={wire}>
      {functionLabelDisplayZh(wire)}
    </span>
  );
}

function SecondaryLabels({ wires }: { wires: string[] }) {
  if (!wires.length) {
    return <span data-testid="cf-secondary-empty">{SECONDARY_EMPTY_MESSAGE}</span>;
  }
  return (
    <span className={styles.tags} data-testid="cf-secondary-labels">
      {wires.map((w) => (
        <span key={w} className={styles.tag} data-wire={w}>
          {functionLabelDisplayZh(w)}
        </span>
      ))}
    </span>
  );
}

function SemanticsNote({ wire }: { wire: string | null }) {
  if (!wire || !isCanonicalFunctionLabel(wire)) return null;
  const note = FUNCTION_LABEL_SEMANTICS_ZH[wire as CanonicalFunctionLabel];
  if (!note) return null;
  return (
    <p className={styles.semanticsNote} data-testid={`cf-semantics-${wire}`}>
      {note}
    </p>
  );
}

export function ChapterFunctionsPanel({
  viewState,
  response,
  items,
  loading,
  loadingMore,
  errorMessage,
  filters,
  onFiltersChange,
  onClearFilters,
  onLoadMore,
  hasMore,
  selectedChapterId,
  detailItem,
  detailLoading,
  onSelectChapter,
  onCloseDetail,
  onOpenEvidence,
  onRetry,
  onBack,
  useDrawerDetail,
}: {
  viewState: ChapterFunctionsClientViewState;
  response: ChapterFunctionsProductResponse | null;
  items: ChapterFunctionItemV2[];
  loading?: boolean;
  loadingMore?: boolean;
  errorMessage?: string | null;
  filters: ChapterFunctionsFilters;
  onFiltersChange: (next: ChapterFunctionsFilters) => void;
  onClearFilters: () => void;
  onLoadMore?: () => void;
  hasMore?: boolean;
  selectedChapterId?: string | null;
  detailItem?: ChapterFunctionItemV2 | null;
  detailLoading?: boolean;
  onSelectChapter: (chapterId: string) => void;
  onCloseDetail?: () => void;
  onOpenEvidence: (evidenceId: number) => void;
  onRetry?: () => void;
  onBack?: () => void;
  /** Force drawer mode (e.g. 1366 harness). Auto when matchMedia if omitted. */
  useDrawerDetail?: boolean;
}) {
  const [drawerMode, setDrawerMode] = useState(Boolean(useDrawerDetail));

  useEffect(() => {
    if (useDrawerDetail != null) {
      setDrawerMode(useDrawerDetail);
      return;
    }
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(max-width: 1366px)");
    const apply = () => setDrawerMode(mq.matches);
    apply();
    mq.addEventListener?.("change", apply);
    return () => mq.removeEventListener?.("change", apply);
  }, [useDrawerDetail]);

  if (viewState === "loading" || loading) {
    return (
      <section
        className={styles.panel}
        data-testid="whole-book-free-chapter-functions"
        data-state="loading"
      >
        <h2>章节功能</h2>
        <p data-testid="whole-book-free-chapter-functions-loading">正在加载章节功能结果…</p>
        <p className={styles.meta}>进度请参见上方全书分析任务状态，不另建独立状态机。</p>
      </section>
    );
  }

  if (viewState === "not_started") {
    return (
      <section
        className={styles.panel}
        data-testid="whole-book-free-chapter-functions"
        data-state="not_started"
      >
        <h2>章节功能</h2>
        <div className={styles.emptyState} data-testid="whole-book-free-chapter-functions-not-started">
          <h3>尚未生成章节功能结果</h3>
          <p>请先开始全书分析。完成后可在此查看逐章功能。</p>
        </div>
      </section>
    );
  }

  if (viewState === "absent") {
    return (
      <section
        className={styles.panel}
        data-testid="whole-book-free-chapter-functions"
        data-state="absent"
      >
        <h2>章节功能</h2>
        <div className={styles.emptyState} data-testid="whole-book-free-chapter-functions-absent">
          <h3>尚未生成章节功能结果</h3>
          <p>
            当前运行尚未产出章节功能结果（CHAPTER_FUNCTIONS_RESULT_ABSENT），这不等于“无数据”。
          </p>
          <div className={styles.actions}>
            {onRetry ? (
              <button
                type="button"
                className="secondary"
                onClick={onRetry}
                data-testid="whole-book-free-chapter-functions-retry"
              >
                重新分析
              </button>
            ) : null}
            {onBack ? (
              <button
                type="button"
                className="secondary"
                onClick={onBack}
                data-testid="whole-book-free-chapter-functions-back"
              >
                返回
              </button>
            ) : null}
          </div>
        </div>
      </section>
    );
  }

  if (viewState === "canceled") {
    return (
      <section
        className={styles.panel}
        data-testid="whole-book-free-chapter-functions"
        data-state="canceled"
      >
        <h2>章节功能</h2>
        <div className={styles.emptyState} data-testid="whole-book-free-chapter-functions-canceled">
          <h3>已取消</h3>
          <p>
            {response?.failure_message_safe ?? "本次全书分析任务已取消，章节功能未完成。"}
          </p>
          <p className={styles.meta}>该状态不是失败，也不是完成。</p>
        </div>
      </section>
    );
  }

  if (viewState === "failed") {
    return (
      <section
        className={styles.panel}
        data-testid="whole-book-free-chapter-functions"
        data-state="failed"
      >
        <h2>章节功能</h2>
        <div className={styles.emptyState} data-testid="whole-book-free-chapter-functions-failed">
          <h3>分析失败</h3>
          <p>{response?.failure_message_safe ?? errorMessage ?? "章节功能分析失败。"}</p>
          {response?.failure_code ? (
            <p className={styles.meta} data-testid="whole-book-free-chapter-functions-failure-code">
              失败码：{response.failure_code}
            </p>
          ) : null}
          <div className={styles.actions}>
            {onRetry ? (
              <button
                type="button"
                className="secondary"
                onClick={onRetry}
                data-testid="whole-book-free-chapter-functions-retry"
              >
                重新分析
              </button>
            ) : null}
          </div>
        </div>
      </section>
    );
  }

  if (viewState === "conflict") {
    return (
      <section
        className={styles.panel}
        data-testid="whole-book-free-chapter-functions"
        data-state="conflict"
      >
        <h2>章节功能</h2>
        <div className={styles.emptyState} data-testid="whole-book-free-chapter-functions-conflict">
          <h3>存在新版本或冲突结果</h3>
          <p>已确认结果不会被静默覆盖。请在保留当前确认版本的前提下处理候选结果。</p>
          {response?.conflict?.versions?.length ? (
            <ul data-testid="whole-book-free-chapter-functions-conflict-versions">
              {response.conflict.versions.map((v) => (
                <li key={String(v.version_id)}>
                  {v.label ?? v.version_id}
                  {v.state ? `（${v.state}）` : ""}
                  {response.conflict?.current_pointer != null &&
                  String(response.conflict.current_pointer) === String(v.version_id)
                    ? " · 当前指针"
                    : ""}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        {items.length ? (
          <AvailableChapterFunctionsBody
            response={response}
            items={items}
            filters={filters}
            onFiltersChange={onFiltersChange}
            onClearFilters={onClearFilters}
            onLoadMore={onLoadMore}
            hasMore={hasMore}
            loadingMore={loadingMore}
            selectedChapterId={selectedChapterId}
            detailItem={detailItem}
            detailLoading={detailLoading}
            onSelectChapter={onSelectChapter}
            onCloseDetail={onCloseDetail}
            onOpenEvidence={onOpenEvidence}
            drawerMode={drawerMode}
            dimmed
          />
        ) : null}
      </section>
    );
  }

  if (viewState === "unsupported_contract") {
    return (
      <section
        className={styles.panel}
        data-testid="whole-book-free-chapter-functions"
        data-state="unsupported_contract"
      >
        <h2>章节功能</h2>
        <div
          className={styles.emptyState}
          data-testid="whole-book-free-chapter-functions-unsupported"
        >
          <h3>合同版本不受支持</h3>
          <p>{errorMessage ?? "当前结果的 contract_version 不是 v2，桌面端拒绝渲染。"}</p>
          <p className={styles.meta}>
            期望：{CHAPTER_FUNCTIONS_CONTRACT_PACKAGE_VERSION} / wire v2
          </p>
        </div>
      </section>
    );
  }

  if (viewState === "network_error") {
    return (
      <section
        className={styles.panel}
        data-testid="whole-book-free-chapter-functions"
        data-state="network_error"
      >
        <h2>章节功能</h2>
        <div
          className={styles.emptyState}
          data-testid="whole-book-free-chapter-functions-network-error"
        >
          <h3>无法加载章节功能</h3>
          <p>{errorMessage ?? "网络错误，请稍后重试。"}</p>
          {onRetry ? (
            <button
              type="button"
              className="secondary"
              onClick={onRetry}
              data-testid="whole-book-free-chapter-functions-retry"
            >
              重试
            </button>
          ) : null}
        </div>
      </section>
    );
  }

  if (viewState === "insufficient") {
    const cf = response?.chapter_functions;
    return (
      <section
        className={styles.panel}
        data-testid="whole-book-free-chapter-functions"
        data-state="insufficient"
      >
        <h2>章节功能</h2>
        <div
          className={styles.emptyState}
          data-testid="whole-book-free-chapter-functions-insufficient"
        >
          <h3>证据不足</h3>
          <p data-testid="whole-book-free-chapter-functions-insufficient-message">
            {INSUFFICIENT_MESSAGE}
          </p>
          <p className={styles.meta}>
            coverage_scope：{response?.coverage_scope ?? cf?.coverage_scope ?? "insufficient"}
          </p>
          {response?.empty_reason || cf?.empty_reason ? (
            <p className={styles.meta} data-testid="whole-book-free-chapter-functions-empty-reason">
              empty reason：{response?.empty_reason ?? cf?.empty_reason}
            </p>
          ) : null}
          {cf?.limitations?.length ? (
            <ul className={styles.limitList} data-testid="whole-book-free-chapter-functions-limitations">
              {cf.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
          <div className={styles.actions}>
            {onRetry ? (
              <button
                type="button"
                className="secondary"
                onClick={onRetry}
                data-testid="whole-book-free-chapter-functions-retry"
              >
                重新分析
              </button>
            ) : null}
            {onBack ? (
              <button
                type="button"
                className="secondary"
                onClick={onBack}
                data-testid="whole-book-free-chapter-functions-back"
              >
                返回
              </button>
            ) : null}
          </div>
        </div>
      </section>
    );
  }

  // available | partial
  return (
    <section
      className={styles.panel}
      data-testid="whole-book-free-chapter-functions"
      data-state={viewState}
    >
      <h2>章节功能</h2>
      {errorMessage ? (
        <p className={styles.partialBanner} data-testid="whole-book-free-chapter-functions-error-banner">
          {errorMessage}
        </p>
      ) : null}
      <AvailableChapterFunctionsBody
        response={response}
        items={items}
        filters={filters}
        onFiltersChange={onFiltersChange}
        onClearFilters={onClearFilters}
        onLoadMore={onLoadMore}
        hasMore={hasMore}
        loadingMore={loadingMore}
        selectedChapterId={selectedChapterId}
        detailItem={detailItem}
        detailLoading={detailLoading}
        onSelectChapter={onSelectChapter}
        onCloseDetail={onCloseDetail}
        onOpenEvidence={onOpenEvidence}
        drawerMode={drawerMode}
        partial={viewState === "partial"}
      />
    </section>
  );
}

function AvailableChapterFunctionsBody({
  response,
  items,
  filters,
  onFiltersChange,
  onClearFilters,
  onLoadMore,
  hasMore,
  loadingMore,
  selectedChapterId,
  detailItem,
  detailLoading,
  onSelectChapter,
  onCloseDetail,
  onOpenEvidence,
  drawerMode,
  dimmed = false,
  partial = false,
}: {
  response: ChapterFunctionsProductResponse | null;
  items: ChapterFunctionItemV2[];
  filters: ChapterFunctionsFilters;
  onFiltersChange: (next: ChapterFunctionsFilters) => void;
  onClearFilters: () => void;
  onLoadMore?: () => void;
  hasMore?: boolean;
  loadingMore?: boolean;
  selectedChapterId?: string | null;
  detailItem?: ChapterFunctionItemV2 | null;
  detailLoading?: boolean;
  onSelectChapter: (chapterId: string) => void;
  onCloseDetail?: () => void;
  onOpenEvidence: (evidenceId: number) => void;
  drawerMode: boolean;
  dimmed?: boolean;
  partial?: boolean;
}) {
  const cf = response?.chapter_functions;
  const confidence = cf?.overall_confidence ?? cf?.analysis_confidence;
  const total = response?.total_chapters ?? cf?.chapters?.length ?? items.length;
  const analyzed =
    response?.analyzed_chapter_count ??
    (partial ? items.length : total);
  const unfinished = response?.unfinished_chapter_count ?? null;

  const selected = useMemo(() => {
    if (detailItem) return detailItem;
    if (!selectedChapterId) return null;
    return items.find((i) => chapterKey(i) === selectedChapterId) ?? null;
  }, [detailItem, items, selectedChapterId]);

  const detailNode = selected ? (
    <ChapterDetail
      item={selected}
      bindings={response?.citation_evidence_bindings}
      loading={detailLoading}
      onOpenEvidence={onOpenEvidence}
      onClose={onCloseDetail}
    />
  ) : (
    <div className={styles.detailPanel} data-testid="whole-book-free-chapter-functions-detail-empty">
      <p className={styles.meta}>选择章节以查看详情</p>
    </div>
  );

  return (
    <div
      data-testid="whole-book-free-chapter-functions-available"
      data-dimmed={dimmed ? "true" : "false"}
      data-partial={partial ? "true" : "false"}
    >
      {partial ? (
        <div className={styles.partialBanner} data-testid="whole-book-free-chapter-functions-partial-banner">
          部分章节结果可用；尚未完成全部章节。
          {unfinished != null ? ` 未完成/不可用约 ${unfinished} 章。` : ""}
          请勿将此状态视为完整完成。
        </div>
      ) : null}

      <dl className={styles.overview} data-testid="whole-book-free-chapter-functions-overview">
        <div className={styles.overviewItem}>
          <dt>coverage_scope</dt>
          <dd data-testid="whole-book-free-chapter-functions-coverage">
            {response?.coverage_scope ?? cf?.coverage_scope ?? "—"}
          </dd>
        </div>
        <div className={styles.overviewItem}>
          <dt>result status</dt>
          <dd data-testid="whole-book-free-chapter-functions-result-status">
            {partial ? "partial（部分可用）" : response?.result_status ?? "—"}
          </dd>
        </div>
        <div className={styles.overviewItem}>
          <dt>已分析 / 总章节</dt>
          <dd data-testid="whole-book-free-chapter-functions-counts">
            {analyzed} / {total}
          </dd>
        </div>
        <div className={styles.overviewItem}>
          <dt>confidence</dt>
          <dd data-testid="whole-book-free-chapter-functions-confidence">
            {formatConfidence(confidence)}
          </dd>
        </div>
        <div className={styles.overviewItem}>
          <dt>limitations</dt>
          <dd data-testid="whole-book-free-chapter-functions-limitations">
            {cf?.limitations?.length ? cf.limitations.join("；") : "无"}
          </dd>
        </div>
        <div className={styles.overviewItem}>
          <dt>source revision</dt>
          <dd data-testid="whole-book-free-chapter-functions-source-revision">
            run {response?.source_revision?.run_id ?? "—"}
            {response?.source_revision?.snapshot_id != null
              ? ` · snapshot ${response.source_revision.snapshot_id}`
              : ""}
            {response?.source_revision?.snapshot_revision
              ? ` · ${response.source_revision.snapshot_revision}`
              : ""}
          </dd>
        </div>
        <div className={styles.overviewItem}>
          <dt>WB-2.1 上下文（可选）</dt>
          <dd data-testid="whole-book-free-chapter-functions-wb21-context">
            {wb21ContextLabel(cf?.context_capabilities ?? null)}
          </dd>
        </div>
      </dl>

      <details className={styles.techDetails} data-testid="whole-book-free-chapter-functions-tech-details">
        <summary>技术详情 / context capabilities</summary>
        <p>
          contract：{cf?.contract_version ?? response?.contract_version ?? "—"} / package{" "}
          {CHAPTER_FUNCTIONS_CONTRACT_PACKAGE_VERSION}
        </p>
        <p>schema_version：{response?.schema_version ?? "—"}</p>
        <p>evidence_contract_version：{cf?.evidence_contract_version ?? "—"}</p>
        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", margin: 0 }}>
          {JSON.stringify(cf?.context_capabilities ?? {}, null, 2)}
        </pre>
      </details>

      <div className={styles.filterBar} data-testid="whole-book-free-chapter-functions-filters">
        <label>
          功能标签
          <select
            data-testid="whole-book-free-chapter-functions-filter-function"
            value={filters.function}
            onChange={(e) => onFiltersChange({ ...filters, function: e.target.value })}
          >
            <option value="">全部功能</option>
            {CANONICAL_FUNCTION_LABELS.map((label) => (
              <option key={label} value={label}>
                {functionLabelDisplayZh(label)}（{label}）
              </option>
            ))}
          </select>
        </label>
        <label>
          章节状态
          <select
            data-testid="whole-book-free-chapter-functions-filter-status"
            value={filters.status}
            onChange={(e) => onFiltersChange({ ...filters, status: e.target.value })}
          >
            {CLAIM_STATUS_OPTIONS.map((opt) => (
              <option key={opt.value || "all"} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="secondary"
          data-testid="whole-book-free-chapter-functions-clear-filters"
          onClick={onClearFilters}
        >
          清除筛选
        </button>
      </div>

      <div
        className={`${styles.workbench} ${drawerMode || !selected ? styles.workbenchSingle : ""}`}
        data-testid="whole-book-free-chapter-functions-workbench"
        data-drawer={drawerMode ? "true" : "false"}
      >
        <div>
          <h3>章节列表（本页 {items.length} / 共 {total}）</h3>
          <ul className={styles.chapterList} data-testid="whole-book-free-chapter-functions-list">
            {items.map((item) => {
              const key = chapterKey(item);
              const evidenceId = firstEvidenceIdForChapter(
                item,
                response?.citation_evidence_bindings,
              );
              return (
                <li key={key}>
                  <div
                    className={styles.chapterRow}
                    role="button"
                    tabIndex={0}
                    data-testid={`whole-book-free-chapter-functions-row-${key}`}
                    data-selected={selectedChapterId === key ? "true" : "false"}
                    onClick={() => onSelectChapter(key)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelectChapter(key);
                      }
                    }}
                  >
                    <h3>
                      #{item.chapter_order} {item.chapter_title || `章节 ${item.chapter_id}`}
                    </h3>
                    <p className={styles.meta}>
                      主要： <PrimaryLabel wire={item.primary_function} />
                    </p>
                    <p className={styles.meta}>
                      辅助： <SecondaryLabels wires={item.secondary_functions ?? []} />
                    </p>
                    <p className={styles.bodyText}>
                      {snippet(item.observed_summary?.value)}
                    </p>
                    <p className={styles.meta}>
                      置信度：{formatConfidence(item.confidence)} · 状态：
                      {item.observed_summary?.status ?? "—"}
                    </p>
                    <SemanticsNote wire={item.primary_function} />
                    <div className={styles.actions}>
                      <button
                        type="button"
                        className="secondary"
                        data-testid={`whole-book-free-chapter-functions-evidence-${key}`}
                        disabled={evidenceId == null}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (evidenceId != null) onOpenEvidence(evidenceId);
                        }}
                      >
                        Evidence
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        data-testid={`whole-book-free-chapter-functions-detail-btn-${key}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectChapter(key);
                        }}
                      >
                        查看详情
                      </button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
          <div className={styles.pagination} data-testid="whole-book-free-chapter-functions-pagination">
            {hasMore ? (
              <button
                type="button"
                data-testid="whole-book-free-chapter-functions-load-more"
                disabled={loadingMore}
                onClick={() => onLoadMore?.()}
              >
                {loadingMore ? "加载中…" : "加载更多"}
              </button>
            ) : (
              <span className={styles.meta} data-testid="whole-book-free-chapter-functions-end">
                已到末页
              </span>
            )}
            {loadingMore ? (
              <span className={styles.meta} data-testid="whole-book-free-chapter-functions-loading-more">
                正在加载下一页…
              </span>
            ) : null}
          </div>
        </div>

        {!drawerMode ? detailNode : null}
      </div>

      {drawerMode && selected ? (
        <div className={styles.detailDrawer} data-testid="whole-book-free-chapter-functions-drawer">
          <div className={styles.detailDrawerInner}>
            <ChapterDetail
              item={selected}
              bindings={response?.citation_evidence_bindings}
              loading={detailLoading}
              onOpenEvidence={onOpenEvidence}
              onClose={onCloseDetail}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ChapterDetail({
  item,
  bindings,
  loading,
  onOpenEvidence,
  onClose,
}: {
  item: ChapterFunctionItemV2;
  bindings: ChapterFunctionsProductResponse["citation_evidence_bindings"];
  loading?: boolean;
  onOpenEvidence: (evidenceId: number) => void;
  onClose?: () => void;
}) {
  const evidenceId = firstEvidenceIdForChapter(item, bindings);
  return (
    <div
      className={styles.detailPanel}
      data-testid="whole-book-free-chapter-functions-detail"
      data-chapter-id={String(item.chapter_id)}
    >
      <div className={styles.actions}>
        {onClose ? (
          <button
            type="button"
            className="secondary"
            data-testid="whole-book-free-chapter-functions-detail-close"
            onClick={onClose}
          >
            关闭详情
          </button>
        ) : null}
      </div>
      {loading ? <p className={styles.meta}>正在加载章节详情…</p> : null}
      <h3>
        #{item.chapter_order} {item.chapter_title || `章节 ${item.chapter_id}`}
      </h3>
      <p className={styles.meta}>
        主要功能： <PrimaryLabel wire={item.primary_function} />
      </p>
      <p className={styles.meta}>
        辅助功能： <SecondaryLabels wires={item.secondary_functions ?? []} />
      </p>
      <SemanticsNote wire={item.primary_function} />
      {item.observed_summary?.value ? (
        <p className={styles.bodyText} data-testid="cf-detail-observed">
          <strong>观察摘要：</strong>
          {item.observed_summary.value}
        </p>
      ) : null}
      {item.inferred_effect?.value ? (
        <p className={styles.bodyText} data-testid="cf-detail-inferred">
          <strong>推断效果：</strong>
          {item.inferred_effect.value}
        </p>
      ) : null}
      <p className={styles.meta}>置信度：{formatConfidence(item.confidence)}</p>
      <p className={styles.meta}>状态：{item.observed_summary?.status ?? "—"}</p>
      {item.limitations?.length ? (
        <ul className={styles.limitList}>
          {item.limitations.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      ) : null}
      <div className={styles.actions}>
        <button
          type="button"
          className="secondary"
          data-testid="whole-book-free-chapter-functions-detail-evidence"
          disabled={evidenceId == null}
          onClick={() => {
            if (evidenceId != null) onOpenEvidence(evidenceId);
          }}
        >
          Evidence
        </button>
      </div>
    </div>
  );
}
