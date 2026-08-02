import type {
  StructureClientViewState,
  StructureProductResponse,
  StructureStageV2,
  TurningPointV2,
} from "../../../services/structureStagesResultV2";
import {
  STRUCTURE_STAGES_CONTRACT_PACKAGE_VERSION,
  collectStageEvidenceCitationIds,
  collectTurningPointEvidenceCitationIds,
  resolveEvidenceIdForCitation,
  stageChapterRange,
} from "../../../services/structureStagesResultV2";
import styles from "./StructureStagesPanel.module.css";

const INSUFFICIENT_MESSAGE =
  "当前原文覆盖或证据不足，暂无法可靠识别全书结构阶段。";
const TP_EMPTY_MESSAGE = "未识别出足够明确的独立转折点";

function formatConfidence(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return String(Math.round(value * 1000) / 1000);
}

function formatChapterRange(start: number | null, end: number | null): string {
  if (start == null && end == null) return "章节范围未知";
  if (start != null && end != null) {
    return start === end ? `第 ${start} 章` : `第 ${start}–${end} 章`;
  }
  if (start != null) return `自第 ${start} 章`;
  return `至第 ${end} 章`;
}

function claimLabel(status: string | undefined): string {
  if (status === "observed") return "观察摘要";
  if (status === "inferred") return "推断含义";
  return "摘要";
}

function firstEvidenceId(
  citationIds: string[],
  bindings: StructureProductResponse["citation_evidence_bindings"],
): number | null {
  for (const cid of citationIds) {
    const eid = resolveEvidenceIdForCitation(cid, bindings);
    if (eid != null) return eid;
  }
  return null;
}

export function StructureStagesPanel({
  viewState,
  response,
  loading,
  errorMessage,
  onOpenEvidence,
  onRetry,
  onBack,
}: {
  viewState: StructureClientViewState;
  response: StructureProductResponse | null;
  loading?: boolean;
  errorMessage?: string | null;
  onOpenEvidence: (evidenceId: number) => void;
  onRetry?: () => void;
  onBack?: () => void;
}) {
  if (viewState === "loading" || loading) {
    return (
      <section className={styles.panel} data-testid="whole-book-free-structure" data-state="loading">
        <h2>故事结构</h2>
        <p data-testid="whole-book-free-structure-loading">正在加载故事结构结果…</p>
        <p className={styles.meta}>进度请参见上方全书分析任务状态，不另建独立状态机。</p>
      </section>
    );
  }

  if (viewState === "not_started") {
    return (
      <section className={styles.panel} data-testid="whole-book-free-structure" data-state="not_started">
        <h2>故事结构</h2>
        <div className={styles.emptyState} data-testid="whole-book-free-structure-not-started">
          <h3>尚未生成故事结构结果</h3>
          <p>请先开始全书分析。完成后可在此查看结构阶段。</p>
        </div>
      </section>
    );
  }

  if (viewState === "absent") {
    return (
      <section className={styles.panel} data-testid="whole-book-free-structure" data-state="absent">
        <h2>故事结构</h2>
        <div className={styles.emptyState} data-testid="whole-book-free-structure-absent">
          <h3>尚未生成故事结构结果</h3>
          <p>当前运行尚未产出故事结构结果（STRUCTURE_RESULT_ABSENT），这不等于“无数据”。</p>
          <div className={styles.actions}>
            {onRetry ? (
              <button type="button" className="secondary" onClick={onRetry} data-testid="whole-book-free-structure-retry">
                重新分析
              </button>
            ) : null}
            {onBack ? (
              <button type="button" className="secondary" onClick={onBack} data-testid="whole-book-free-structure-back">
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
      <section className={styles.panel} data-testid="whole-book-free-structure" data-state="canceled">
        <h2>故事结构</h2>
        <div className={styles.emptyState} data-testid="whole-book-free-structure-canceled">
          <h3>已取消</h3>
          <p>{response?.failure_message_safe ?? "本次全书分析任务已取消，故事结构未完成。"}</p>
          <p className={styles.meta}>该状态不是失败，也不是完成。</p>
        </div>
      </section>
    );
  }

  if (viewState === "failed") {
    return (
      <section className={styles.panel} data-testid="whole-book-free-structure" data-state="failed">
        <h2>故事结构</h2>
        <div className={styles.emptyState} data-testid="whole-book-free-structure-failed">
          <h3>分析失败</h3>
          <p>{response?.failure_message_safe ?? errorMessage ?? "故事结构分析失败。"}</p>
          {response?.failure_code ? (
            <p className={styles.meta} data-testid="whole-book-free-structure-failure-code">
              失败码：{response.failure_code}
            </p>
          ) : null}
          <div className={styles.actions}>
            {onRetry ? (
              <button type="button" className="secondary" onClick={onRetry} data-testid="whole-book-free-structure-retry">
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
      <section className={styles.panel} data-testid="whole-book-free-structure" data-state="conflict">
        <h2>故事结构</h2>
        <div className={styles.emptyState} data-testid="whole-book-free-structure-conflict">
          <h3>存在新版本或冲突结果</h3>
          <p>
            已确认结果不会被静默覆盖。请在保留当前确认版本的前提下处理候选结果。
          </p>
          {response?.conflict?.versions?.length ? (
            <ul data-testid="whole-book-free-structure-conflict-versions">
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
        {response?.structure ? (
          <AvailableStructureBody
            response={response}
            onOpenEvidence={onOpenEvidence}
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
        data-testid="whole-book-free-structure"
        data-state="unsupported_contract"
      >
        <h2>故事结构</h2>
        <div className={styles.emptyState} data-testid="whole-book-free-structure-unsupported">
          <h3>合同版本不受支持</h3>
          <p>{errorMessage ?? "当前结果的 contract_version 不是 v2，桌面端拒绝渲染。"}</p>
          <p className={styles.meta}>期望：{STRUCTURE_STAGES_CONTRACT_PACKAGE_VERSION} / wire v2</p>
        </div>
      </section>
    );
  }

  if (viewState === "network_error") {
    return (
      <section className={styles.panel} data-testid="whole-book-free-structure" data-state="network_error">
        <h2>故事结构</h2>
        <div className={styles.emptyState} data-testid="whole-book-free-structure-network-error">
          <h3>无法加载故事结构</h3>
          <p>{errorMessage ?? "网络错误，请稍后重试。"}</p>
          {onRetry ? (
            <button type="button" className="secondary" onClick={onRetry} data-testid="whole-book-free-structure-retry">
              重试
            </button>
          ) : null}
        </div>
      </section>
    );
  }

  if (viewState === "insufficient") {
    const structure = response?.structure;
    return (
      <section className={styles.panel} data-testid="whole-book-free-structure" data-state="insufficient">
        <h2>故事结构</h2>
        <div className={styles.emptyState} data-testid="whole-book-free-structure-insufficient">
          <h3>证据不足</h3>
          <p data-testid="whole-book-free-structure-insufficient-message">{INSUFFICIENT_MESSAGE}</p>
          <p className={styles.meta}>
            coverage_scope：{response?.coverage_scope ?? structure?.coverage_scope ?? "insufficient"}
          </p>
          {response?.empty_reason ? (
            <p className={styles.meta} data-testid="whole-book-free-structure-empty-reason">
              empty reason：{response.empty_reason}
            </p>
          ) : null}
          {structure?.limitations?.length ? (
            <ul className={styles.limitList} data-testid="whole-book-free-structure-limitations">
              {structure.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
          <div className={styles.actions}>
            {onRetry ? (
              <button type="button" className="secondary" onClick={onRetry} data-testid="whole-book-free-structure-retry">
                重新分析
              </button>
            ) : null}
            {onBack ? (
              <button type="button" className="secondary" onClick={onBack} data-testid="whole-book-free-structure-back">
                返回
              </button>
            ) : null}
          </div>
        </div>
      </section>
    );
  }

  // available
  if (!response?.structure) {
    return (
      <section className={styles.panel} data-testid="whole-book-free-structure" data-state="absent">
        <h2>故事结构</h2>
        <p>尚未生成故事结构结果</p>
      </section>
    );
  }

  return (
    <section className={styles.panel} data-testid="whole-book-free-structure" data-state="available">
      <h2>故事结构</h2>
      <AvailableStructureBody response={response} onOpenEvidence={onOpenEvidence} />
    </section>
  );
}

function AvailableStructureBody({
  response,
  onOpenEvidence,
  dimmed = false,
}: {
  response: StructureProductResponse;
  onOpenEvidence: (evidenceId: number) => void;
  dimmed?: boolean;
}) {
  const structure = response.structure!;
  const stages = structure.stages ?? [];
  const turningPoints = structure.turning_points ?? [];
  const confidence = structure.overall_confidence ?? structure.analysis_confidence;

  return (
    <div data-testid="whole-book-free-structure-available" data-dimmed={dimmed ? "true" : "false"}>
      <dl className={styles.overview} data-testid="whole-book-free-structure-overview">
        <div className={styles.overviewItem}>
          <dt>coverage_scope</dt>
          <dd data-testid="whole-book-free-structure-coverage">{structure.coverage_scope}</dd>
        </div>
        <div className={styles.overviewItem}>
          <dt>confidence</dt>
          <dd data-testid="whole-book-free-structure-confidence">{formatConfidence(confidence)}</dd>
        </div>
        <div className={styles.overviewItem}>
          <dt>limitations</dt>
          <dd data-testid="whole-book-free-structure-limitations">
            {structure.limitations?.length ? structure.limitations.join("；") : "无"}
          </dd>
        </div>
        <div className={styles.overviewItem}>
          <dt>source revision</dt>
          <dd data-testid="whole-book-free-structure-source-revision">
            run {response.source_revision?.run_id ?? "—"}
            {response.source_revision?.snapshot_id != null
              ? ` · snapshot ${response.source_revision.snapshot_id}`
              : ""}
            {response.source_revision?.snapshot_revision
              ? ` · ${response.source_revision.snapshot_revision}`
              : ""}
          </dd>
        </div>
      </dl>

      <details className={styles.techDetails} data-testid="whole-book-free-structure-tech-details">
        <summary>技术详情 / context capabilities</summary>
        <p>contract：{structure.contract_version} / package {STRUCTURE_STAGES_CONTRACT_PACKAGE_VERSION}</p>
        <p>evidence_contract_version：{structure.evidence_contract_version}</p>
        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", margin: 0 }}>
          {JSON.stringify(structure.context_capabilities ?? {}, null, 2)}
        </pre>
      </details>

      <section>
        <h3>阶段列表（{stages.length}）</h3>
        <ul className={styles.stageGrid} data-testid="whole-book-free-structure-stage-list">
          {stages.map((stage) => (
            <StageCard
              key={stage.local_stage_ref}
              stage={stage}
              bindings={response.citation_evidence_bindings}
              onOpenEvidence={onOpenEvidence}
            />
          ))}
        </ul>
      </section>

      <section>
        <h3>转折点</h3>
        {turningPoints.length === 0 ? (
          <p className={styles.meta} data-testid="whole-book-free-structure-tp-empty">
            {TP_EMPTY_MESSAGE}
          </p>
        ) : (
          <ul className={styles.tpList} data-testid="whole-book-free-structure-tp-list">
            {turningPoints.map((tp) => (
              <TurningPointCard
                key={tp.local_turning_point_ref}
                tp={tp}
                bindings={response.citation_evidence_bindings}
                onOpenEvidence={onOpenEvidence}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function StageCard({
  stage,
  bindings,
  onOpenEvidence,
}: {
  stage: StructureStageV2;
  bindings: StructureProductResponse["citation_evidence_bindings"];
  onOpenEvidence: (evidenceId: number) => void;
}) {
  const { start, end } = stageChapterRange(stage);
  const evidenceId = firstEvidenceId(collectStageEvidenceCitationIds(stage), bindings);
  const summaryStatus = String(stage.summary?.status ?? "");
  const showObserved = summaryStatus === "observed";
  const showInferred = summaryStatus === "inferred" || Boolean(stage.narrative_function);

  return (
    <li
      className={styles.stageCard}
      data-testid={`whole-book-free-structure-stage-${stage.local_stage_ref}`}
    >
      <h3>{stage.title}</h3>
      <p className={styles.meta}>{formatChapterRange(start, end)}</p>
      {showObserved && stage.summary?.value ? (
        <p className={styles.bodyText}>
          <strong>{claimLabel("observed")}：</strong>
          {stage.summary.value}
        </p>
      ) : null}
      {showInferred ? (
        <p className={styles.bodyText}>
          <strong>{claimLabel("inferred")}：</strong>
          {summaryStatus === "inferred" && stage.summary?.value
            ? stage.summary.value
            : stage.narrative_function || "—"}
        </p>
      ) : null}
      <p className={styles.meta}>置信度：{formatConfidence(stage.confidence ?? stage.summary?.confidence)}</p>
      <p className={styles.meta}>
        边界：起 {stage.start_boundary?.value ?? "—"} · 止 {stage.end_boundary?.value ?? "—"}
      </p>
      <div className={styles.actions}>
        <button
          type="button"
          className="secondary"
          data-testid={`whole-book-free-structure-stage-evidence-${stage.local_stage_ref}`}
          disabled={evidenceId == null}
          onClick={() => {
            if (evidenceId != null) onOpenEvidence(evidenceId);
          }}
        >
          Evidence
        </button>
      </div>
    </li>
  );
}

function TurningPointCard({
  tp,
  bindings,
  onOpenEvidence,
}: {
  tp: TurningPointV2;
  bindings: StructureProductResponse["citation_evidence_bindings"];
  onOpenEvidence: (evidenceId: number) => void;
}) {
  const evidenceId = firstEvidenceId(collectTurningPointEvidenceCitationIds(tp), bindings);
  return (
    <li
      className={styles.tpCard}
      data-testid={`whole-book-free-structure-tp-${tp.local_turning_point_ref}`}
    >
      <h3>{tp.title}</h3>
      <p className={styles.meta}>
        {tp.turning_point_type ? `类型：${tp.turning_point_type} · ` : ""}
        {tp.chapter_id != null ? `第 ${tp.chapter_id} 章` : "章节未知"}
      </p>
      {tp.description?.value ? <p className={styles.bodyText}>{tp.description.value}</p> : null}
      <p className={styles.meta}>置信度：{formatConfidence(tp.confidence ?? tp.description?.confidence)}</p>
      <div className={styles.actions}>
        <button
          type="button"
          className="secondary"
          data-testid={`whole-book-free-structure-tp-evidence-${tp.local_turning_point_ref}`}
          disabled={evidenceId == null}
          onClick={() => {
            if (evidenceId != null) onOpenEvidence(evidenceId);
          }}
        >
          Evidence
        </button>
      </div>
    </li>
  );
}
