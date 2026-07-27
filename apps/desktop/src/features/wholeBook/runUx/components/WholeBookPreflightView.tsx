import { Button } from "../../../../components/ui/Button";
import type { WholeBookPreflightPageModel } from "../../contracts/preflight";
import type {
  WholeBookAnalysisMode,
  WholeBookModuleKey,
} from "../../contracts/keys";
import type { PreflightLoadError, StagePlanPreviewRow } from "../types";
import { WholeBookModeSelector } from "./WholeBookModeSelector";
import { WholeBookModuleSelector } from "./WholeBookModuleSelector";
import { WholeBookStagePlanPreview } from "./WholeBookStagePlanPreview";
import { WholeBookBlockingReasonsPanel } from "./WholeBookBlockingReasonsPanel";

export type WholeBookPreflightViewProps = {
  model: WholeBookPreflightPageModel | null;
  loading?: boolean;
  error?: PreflightLoadError | null;
  supportedModes: readonly WholeBookAnalysisMode[];
  stagePlanRows: readonly StagePlanPreviewRow[];
  modeDisabledReasons?: Partial<Record<WholeBookAnalysisMode, string>>;
  onModeChange: (mode: WholeBookAnalysisMode) => void;
  onModulesChange: (modules: WholeBookModuleKey[]) => void;
  onRefresh: () => void;
  onBackToBook?: () => void;
  onViewPreview?: () => void;
  onViewSnapshot?: () => void;
};

export function WholeBookPreflightView({
  model,
  loading = false,
  error = null,
  supportedModes,
  stagePlanRows,
  modeDisabledReasons,
  onModeChange,
  onModulesChange,
  onRefresh,
  onBackToBook,
  onViewPreview,
  onViewSnapshot,
}: WholeBookPreflightViewProps) {
  if (loading) {
    return (
      <div
        className="wb-run-ux__panel"
        data-testid="whole-book-preflight-view"
        data-status="loading"
        role="status"
        aria-busy="true"
        aria-live="polite"
      >
        正在加载 Preflight 检查…
      </div>
    );
  }

  if (error && !model) {
    return (
      <div
        className="wb-run-ux__panel"
        data-testid="whole-book-preflight-view"
        data-status="error"
        role="alert"
      >
        <h2>Preflight 失败（fail-closed）</h2>
        <p>
          {error.code}: {error.message}
        </p>
        <p>离线或网络失败时默认不允许启动，不会开放真实 Run。</p>
        <Button type="button" variant="secondary" onClick={onRefresh}>
          刷新检查
        </Button>
      </div>
    );
  }

  if (!model) {
    return (
      <div
        className="wb-run-ux__panel"
        data-testid="whole-book-preflight-view"
        data-status="empty"
        role="status"
      >
        暂无 Preflight 数据
      </div>
    );
  }

  const bookNotFound = model.blocking_reasons.includes("BOOK_NOT_FOUND");
  const needsSnapshot =
    model.book.snapshot_rebuild_required ||
    model.snapshot.snapshot_id == null ||
    model.warnings.some(
      (w) => w.includes("快照") || w.toLowerCase().includes("snapshot"),
    );
  const startDisabled = !model.effective_run_creation_enabled; // Phase 1D: always false
  const startReason = model.blocking_reasons.length
    ? model.blocking_reasons.join("；")
    : "effective_run_creation_enabled=false";

  return (
    <div
      className="wb-run-ux__panel"
      data-testid="whole-book-preflight-view"
      data-status={model.blocking_reasons.length ? "blocked" : "preview"}
      data-run-creation-enabled={
        model.effective_run_creation_enabled ? "true" : "false"
      }
      data-backend-run-creation-enabled={
        model.backend_run_creation_enabled ? "true" : "false"
      }
      data-client-run-creation-enabled={
        model.client_run_creation_enabled ? "true" : "false"
      }
    >
      <header className="wb-run-ux__header">
        <h1>整书分析 Preflight（原型）</h1>
        <p className="wb-run-ux__hint">
          只读检查，不创建 AnalysisRun / Snapshot，不调用模型。
        </p>
      </header>

      {bookNotFound ? (
        <div className="wb-blocking" role="alert" data-testid="book-not-found">
          未知书籍：找不到 book_id={model.book.book_id}。请返回书库重新选择。
        </div>
      ) : null}

      <section
        className="wb-run-ux__section"
        aria-labelledby="wb-book-heading"
        data-testid="preflight-book-section"
      >
        <h2 id="wb-book-heading">书籍状态</h2>
        <dl className="wb-kv">
          <div>
            <dt>书名</dt>
            <dd className="wb-wrap">{model.book.title}</dd>
          </div>
          <div>
            <dt>章节 / 段落 / 字数</dt>
            <dd>
              {model.book.chapter_count} / {model.book.paragraph_count} /{" "}
              {model.book.character_count}
            </dd>
          </div>
          <div>
            <dt>Snapshot</dt>
            <dd>
              {model.snapshot.snapshot_id != null
                ? `#${model.snapshot.snapshot_id}（${model.snapshot.status ?? "unknown"}）`
                : "无"}
              {model.snapshot.created_at
                ? ` · ${model.snapshot.created_at}`
                : ""}
            </dd>
          </div>
          <div>
            <dt>正文变更</dt>
            <dd>
              {model.book.body_changed_since_snapshot ? "是" : "否"}
              {needsSnapshot ? (
                <span className="wb-run-ux__warn" data-testid="snapshot-required">
                  {" "}
                  — 需要建立快照（不会自动创建）
                </span>
              ) : null}
            </dd>
          </div>
        </dl>
      </section>

      <WholeBookModeSelector
        value={model.analysis_mode}
        supportedModes={supportedModes}
        disabledReasons={modeDisabledReasons}
        sourceCoverage={model.source_coverage}
        onChange={onModeChange}
      />

      <WholeBookModuleSelector
        requestedModules={model.requested_modules}
        resolvedModules={model.resolved_modules}
        autoFillNotes={model.auto_fill_notes}
        onChange={onModulesChange}
      />

      <WholeBookStagePlanPreview rows={stagePlanRows} />

      <section
        className="wb-run-ux__section"
        aria-labelledby="wb-confirm-heading"
        data-testid="preflight-confirm-section"
      >
        <h2 id="wb-confirm-heading">启动确认</h2>
        <dl className="wb-kv">
          <div>
            <dt>Capability</dt>
            <dd className="wb-wrap">
              {model.capability.capability_key} · allowed=
              {String(model.capability.allowed)} · {model.capability.reason_code}
              {" — "}
              {model.capability.message}
            </dd>
          </div>
          <div>
            <dt>License / Availability</dt>
            <dd>{model.capability.availability}</dd>
          </div>
          <div>
            <dt>Quota</dt>
            <dd>
              allowed={String(model.quota.allowed)}
              {model.quota.reason_code ? ` · ${model.quota.reason_code}` : ""}
            </dd>
          </div>
          <div>
            <dt>Engine</dt>
            <dd className="wb-wrap">
              available={String(model.engine.available)} ·{" "}
              {model.engine.message}
            </dd>
          </div>
          <div>
            <dt>预计用量（估算）</dt>
            <dd>
              耗时等级 {model.estimated_usage.estimated_duration_class}；Token /
              费用未给出精确值时显示为 —
            </dd>
          </div>
        </dl>

        <WholeBookBlockingReasonsPanel
          blockingReasons={model.blocking_reasons}
          warnings={model.warnings}
          runCreationEnabled={model.effective_run_creation_enabled}
          backendRunCreationEnabled={model.backend_run_creation_enabled}
          clientRunCreationEnabled={model.client_run_creation_enabled}
          effectiveRunCreationEnabled={model.effective_run_creation_enabled}
        />

        <div className="wb-confirm-actions" data-testid="preflight-actions">
          <Button
            type="button"
            variant="primary"
            disabled={startDisabled}
            title={startReason}
            aria-disabled="true"
            data-testid="start-whole-book-analysis"
            data-force-start="false"
          >
            开始整书分析（已禁用）
          </Button>
          <span className="wb-visually-hidden" role="status">
            开始按钮已禁用：{startReason}
          </span>
          {/* No force-start control exists by design */}
          <Button
            type="button"
            variant="secondary"
            data-testid="refresh-preflight"
            onClick={onRefresh}
          >
            刷新检查
          </Button>
          {onBackToBook ? (
            <Button
              type="button"
              variant="ghost"
              data-testid="back-to-book"
              onClick={onBackToBook}
            >
              返回书籍
            </Button>
          ) : null}
          {onViewPreview ? (
            <Button
              type="button"
              variant="ghost"
              data-testid="view-feature-preview"
              onClick={onViewPreview}
            >
              查看功能预览
            </Button>
          ) : null}
          {onViewSnapshot ? (
            <Button
              type="button"
              variant="ghost"
              data-testid="view-snapshot-status"
              onClick={onViewSnapshot}
            >
              查看 Snapshot 状态
            </Button>
          ) : null}
        </div>
      </section>
    </div>
  );
}
