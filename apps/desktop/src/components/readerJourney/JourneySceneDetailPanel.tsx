import { useMemo, useState } from "react";
import type {
  JourneyPhaseVisualization,
  JourneyQuestionCluster,
  JourneyRiskInterval,
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import {
  formatJourneySceneLabel,
  formatJourneySceneRangeLabel,
  formatJourneyPhaseLabel,
  formatJourneyRiskSummary,
  formatJourneyRiskTypeLabel,
  hookTypeZh,
  payoffTypeZh,
  questionLifecycleZh,
  resolvePhaseSummaryDisplay,
  roleLabelZh,
} from "./journeyUiLabels";
import {
  JourneyCompactMetrics,
  JourneyEvidenceList,
  JourneyInspectorBody,
  JourneyInspectorEmptyState,
  JourneyInspectorHeader,
  JourneyInspectorSection,
  JourneyInspectorShell,
  JourneyInspectorTabs,
  JourneyPrimaryConclusion,
  JourneyRelatedObjectList,
  type EvidenceRow,
} from "./inspectorShell";
import { buildChapterSkeleton, skeletonLedgerNote } from "./chapterSkeleton";
import type { ObservationLensId } from "./observationLenses";
import { DEFAULT_OBSERVATION_LENS } from "./observationLenses";
import {
  findHookResolutionRow,
  type HookResolutionRow,
} from "./hookResolutionModel";
import { isHookPayoffLens } from "./hookPayoffLensModel";
import { deriveChapterHookSceneInsightV1 } from "./chapterHookSimplification";
import {
  dimensionInsightTitle,
  resolveDimensionInsightText,
} from "./dimensionInsights";
import {
  formatLensBindingCaption,
  resolveLensMetricBinding,
} from "./lensMetricBinding";
import { buildSceneNarrative } from "./journeySceneNarrative";
import {
  formatOpenLoopRiskSummary,
  getNarrativeLoopConsistency,
  getNarrativeLoopRisks,
} from "./narrativeLoopView";
import { useDeveloperModeStore } from "../../stores/developerModeStore";

export type SceneDetailTab =
  | "overview"
  | "questions"
  | "payoffs"
  | "techniques"
  | "evidence";

type Props = {
  node: JourneySceneNode;
  onLocateEvidence: (paragraphId: string) => void;
  onClose?: () => void;
  onOpenInSceneList?: () => void;
  visualization?: ReaderJourneyVisualization | null;
  observationLensLabel?: string | null;
  observationLens?: ObservationLensId | null;
  /** When set on 钩子回收 lens, show ordinary-language hook resolution evidence. */
  selectedLoopId?: string | null;
  /** Shared ChapterHookPresentationV1 — avoids independent score/diagnosis inference. */
  hookPresentation?: import("./chapterHookSimplification").ChapterHookSimplificationModel | null;
};

function HookResolutionEvidenceSection({ row }: { row: HookResolutionRow }) {
  return (
    <JourneyInspectorSection title="当前结论" testId="hook-resolution-evidence">
      <div className="hook-resolution-evidence">
        <p data-testid="hook-resolution-evidence-conclusion">{row.main_label}。</p>
        <p data-testid="hook-resolution-evidence-why">
          <b>为什么这样判断</b>
          <br />
          {row.why_judgment_plain}
        </p>
        {row.has_conflict && row.conflict_divergence_plain ? (
          <p data-testid="hook-resolution-evidence-divergence">
            <b>判定分歧</b>
            <br />
            {row.conflict_divergence_plain}
          </p>
        ) : null}
        {row.conflict_tech_reason ? (
          <details data-testid="hook-resolution-evidence-tech">
            <summary>分析信息</summary>
            <pre>{row.conflict_tech_reason}</pre>
          </details>
        ) : null}
      </div>
    </JourneyInspectorSection>
  );
}

const CRAFT_FLAG_LABELS: Record<string, string> = {
  causal_gap: "因果缺口",
  setup_contradiction: "设定矛盾",
  unclear_reference: "指代不明",
  redundant_passage: "重复段落",
};

export function JourneySceneDetailPanel({
  node,
  onLocateEvidence,
  onClose,
  onOpenInSceneList,
  visualization = null,
  observationLens = DEFAULT_OBSERVATION_LENS,
  selectedLoopId = null,
  hookPresentation = null,
}: Props) {
  const developerMode = useDeveloperModeStore((state) => state.developerMode);

  const hookResolutionRow = useMemo(() => {
    if (!visualization || !isHookPayoffLens(observationLens) || !selectedLoopId) {
      return null;
    }
    return findHookResolutionRow(visualization, selectedLoopId);
  }, [visualization, observationLens, selectedLoopId]);

  const hookSceneInsight = useMemo(() => {
    if (!visualization || !isHookPayoffLens(observationLens)) return null;
    return deriveChapterHookSceneInsightV1({
      visualization,
      sceneOrdinal: node.scene_ordinal,
      node,
      presentation: hookPresentation,
    });
  }, [visualization, observationLens, node, hookPresentation]);

  const evidenceRows = useMemo(() => {
    const rows: EvidenceRow[] = [];
    const push = (ids: string[] | undefined, conclusion: string, kind: string) => {
      for (const paragraphId of ids ?? []) {
        if (!paragraphId) continue;
        rows.push({ paragraphId, conclusion, kind });
      }
    };
    push(node.evidence_paragraph_ids, "场景结论", "scene");
    for (const q of node.reader_question_created ?? []) {
      push(q.evidence_paragraph_ids, q.question ?? "问题", "question");
    }
    for (const q of node.reader_question_answered ?? []) {
      push(q.evidence_paragraph_ids, q.question ?? "回答", "question");
    }
    for (const p of node.payoffs ?? []) {
      push(p.evidence_paragraph_ids, p.summary ?? "回应", "payoff");
    }
    for (const h of node.hooks ?? []) {
      push(h.evidence_paragraph_ids, h.summary ?? "悬念", "hook");
    }
    if (node.primary_hook) {
      push(node.primary_hook.evidence_paragraph_ids, node.primary_hook.summary ?? "主悬念", "hook");
    }
    const seen = new Set<string>();
    return rows.filter((row) => {
      const key = `${row.paragraphId}|${row.kind}|${row.conclusion}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [node]);

  if ((node as { integrity_blocked?: boolean }).integrity_blocked) {
    return (
      <JourneyInspectorShell testId="journey-scene-integrity-blocked">
        <JourneyInspectorHeader
          title="分析结果校验未通过"
          meta={formatJourneySceneLabel(node.scene_ordinal)}
        />
        <JourneyInspectorBody>
          <p data-testid="journey-integrity-message">
            {(node as { overview?: string }).overview ||
              "检测到部分结论与当前正文不一致，相关结果已暂停展示。"}
          </p>
          <div className="journey-integrity-actions">
            <button type="button" className="secondary" data-testid="journey-integrity-details">
              查看校验详情
            </button>
            <button
              type="button"
              className="secondary"
              data-testid="journey-integrity-regen"
              disabled
              title="需用户确认后才会调用模型"
            >
              重新生成受影响结果
            </button>
            {onClose ? (
              <button type="button" className="ghost" onClick={onClose}>
                返回正文
              </button>
            ) : null}
          </div>
          <p className="secondary" data-testid="journey-integrity-tech">
            error_code=
            {(node as { integrity_status?: string }).integrity_status || "DATA_INTEGRITY_FAILED"}
            {typeof node.scene_id === "number" ? ` · scene_id=${node.scene_id}` : ""}
          </p>
        </JourneyInspectorBody>
      </JourneyInspectorShell>
    );
  }

  const role = roleLabelZh(node.final_level ?? node.role);
  const sceneRole = node.scene_role ? roleLabelZh(node.scene_role) : role;

  const skeleton = useMemo(
    () => buildChapterSkeleton(visualization?.scene_nodes ?? []),
    [visualization],
  );
  const skeletonNote = useMemo(
    () => skeletonLedgerNote(visualization?.scene_nodes ?? []),
    [visualization],
  );
  /** This scene's own row — the panel's headline is 「它做了什么、占了多少」. */
  const mySkeleton = useMemo(
    () => skeleton.find((row) => row.ordinal === node.scene_ordinal) ?? null,
    [skeleton, node.scene_ordinal],
  );
  const leadMeta = mySkeleton
    ? `${sceneRole} · P${mySkeleton.paragraphFrom}–${mySkeleton.paragraphTo} · 占全章 ${mySkeleton.sharePercent.toFixed(0)}%`
    : `${sceneRole} · ${formatJourneySceneRangeLabel(node.scene_ordinal)}`;
  const mainCurveLabel = visualization?.main_curve?.label || "综合阅读";
  const mainValue = useMemo(() => {
    const raw = (node.scores as Record<string, unknown> | undefined)?.reading_momentum;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  }, [node]);

  const insightTitle = isHookPayoffLens(observationLens)
    ? "钩子洞察"
    : dimensionInsightTitle(observationLens ?? DEFAULT_OBSERVATION_LENS);
  const insightText = isHookPayoffLens(observationLens)
    ? hookSceneInsight?.body || "本场景暂无可靠的钩子洞察。"
    : resolveDimensionInsightText(node, observationLens ?? DEFAULT_OBSERVATION_LENS);
  const lensBinding =
    visualization != null
      ? resolveLensMetricBinding(visualization, observationLens ?? DEFAULT_OBSERVATION_LENS, node)
      : null;
  const narrative =
    visualization != null ? buildSceneNarrative(visualization, node) : null;

  const headerTitle = isHookPayoffLens(observationLens)
    ? hookSceneInsight?.title || `${formatJourneySceneLabel(node.scene_ordinal)} · 钩子洞察`
    : // The role is stated once, in the meta line. Repeating it in the title left the
      // scene number and its role each said twice above a headline that was said once.
      formatJourneySceneLabel(node.scene_ordinal);

  return (
    <JourneyInspectorShell
      testId="journey-detail-drawer"
      className="journey-scene-detail-panel"
    >
      <JourneyInspectorHeader
        title={headerTitle}
        meta={
          isHookPayoffLens(observationLens)
            ? `场景角色：${sceneRole}`
            : leadMeta
        }
        // The role used to appear as a pill *and* in the meta line while the scene's actual
        // move sat below in small type. One mention, in the quietest place.
        pills={[]}
        onClose={onClose}
        titleTestId="scene-detail-title"
      />

      <JourneyInspectorBody>
        {/* 一个焦点，而不是八块等重的内容。头部回答「这一场做了什么、占了多少」——
            功能与篇幅是读者真正要判断的两件事；其余全部降级为它的证据。 */}
        <div className="scene-lead" data-testid="scene-lead">
          <p className="scene-lead-fn" data-testid="scene-lead-function">
            <b data-skippable={mySkeleton?.skippable ?? false}>
              {mySkeleton ? mySkeleton.function : sceneRole}
            </b>
            {mySkeleton ? <span>{mySkeleton.basis}</span> : null}
          </p>
          <p className="scene-lead-stats" data-testid="scene-lead-stats">
            <span>
              {mainCurveLabel}
              <b>{mainValue == null ? "—" : Math.round(mainValue)}</b>
            </span>
            <span>
              读者背着
              <b data-zero={node.open_questions?.balance === 0}>
                {node.open_questions ? node.open_questions.balance : "—"}
              </b>
              {node.open_questions
                ? `（开${node.open_questions.opened} 收${node.open_questions.closed}）`
                : ""}
            </span>
          </p>
        </div>

        {/* 模型原话。折叠而不是删：它是内容，但它是这一屏里面积最大、行话最多的一块
            （「综合阅读贡献偏减」这类措辞），摊开时眼睛必然先落在它上面，而它恰恰不是
            读者要的答案。 */}
        <details className="scene-fold scene-detail-insight-panel" data-testid="scene-detail-insight-panel">
          <summary>模型对这一场的原话</summary>
          {isHookPayoffLens(observationLens) ? (
            <JourneyInspectorSection title="钩子洞察" testId="scene-hook-insight">
              <p data-testid="scene-hook-insight-text">{insightText}</p>
            </JourneyInspectorSection>
          ) : (
            <JourneyInspectorSection title={insightTitle} testId="scene-dimension-insight">
              <p data-testid="scene-dimension-insight-text">{insightText}</p>
              {(observationLens ?? DEFAULT_OBSERVATION_LENS) === "composite" ? (
                <ul
                  className="journey-comprehensive-factor-list"
                  data-testid="scene-comprehensive-factors"
                >
                  {node.composite_role_fit ? (
                    <li data-testid="scene-composite-fit-inline">适配 {node.composite_role_fit}</li>
                  ) : null}
                  {node.primary_driver ? (
                    <li data-testid="scene-primary-driver">推动：{node.primary_driver}</li>
                  ) : null}
                  {node.primary_drag ? (
                    <li data-testid="scene-primary-drag">拖累：{node.primary_drag}</li>
                  ) : null}
                </ul>
              ) : null}
            </JourneyInspectorSection>
          )}
        </details>

        {node.genre_axes?.length ? (
          <JourneyInspectorSection title="类型专项" testId="scene-genre-axes">
            {/* These axes exist because this book's profile asked for them — 悬疑 gets
                线索投放/信息公平, 爽文 gets 爽点兑现/憋屈控制. They sit above the fold rather
                than in 技术详情 because for a reader of that type they are the reading. */}
            <ul className="scene-genre-axis-list" data-testid="scene-genre-axis-list">
              {node.genre_axes.map((axis) => (
                <li key={axis.key} data-testid={`scene-genre-axis-${axis.key}`}>
                  <span className="scene-genre-axis-head">
                    <span className="scene-genre-axis-label">{axis.label}</span>
                    <span className="scene-genre-axis-level" data-level={axis.level}>
                      {axis.level} / 5
                    </span>
                  </span>
                  {axis.rationale ? (
                    <span className="scene-genre-axis-reason">{axis.rationale}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </JourneyInspectorSection>
        ) : null}

        {node.craft_flags?.length ? (
          <JourneyInspectorSection title="需要留意" testId="scene-craft-flags">
            <ul className="scene-craft-flag-list" data-testid="scene-craft-flag-list">
              {node.craft_flags.map((flag, index) => (
                <li key={`${flag.kind}-${index}`}>
                  <span className="scene-craft-flag-kind">{CRAFT_FLAG_LABELS[flag.kind]}</span>
                  <span className="scene-craft-flag-detail">{flag.detail}</span>
                </li>
              ))}
            </ul>
          </JourneyInspectorSection>
        ) : null}

        {skeleton.length ? (
          <details className="scene-fold" data-testid="scene-chapter-skeleton">
            <summary>这一章的骨架 · {skeleton.length} 个动作</summary>
            {/* 每一行说的是一个「动作」和它花掉的篇幅，不是分数——篇幅是能迁移到别的稿子上
                的那部分。全部由程序从既有数据推出，不调模型。 */}
            {skeletonNote ? (
              <p className="skeleton-note" data-testid="scene-skeleton-note">
                {skeletonNote}
              </p>
            ) : null}
            <ol className="skeleton-list" data-testid="scene-skeleton-list">
              {skeleton.map((row) => (
                <li
                  key={row.ordinal}
                  data-testid={`scene-skeleton-row-${row.ordinal}`}
                  data-current={row.ordinal === node.scene_ordinal}
                  data-skippable={row.skippable}
                >
                  <span className="skeleton-fn">{row.function}</span>
                  <span className="skeleton-span">
                    {row.paragraphFrom != null && row.paragraphTo != null
                      ? `P${row.paragraphFrom}–${row.paragraphTo}`
                      : `S${row.ordinal}`}
                  </span>
                  <span className="skeleton-share">{row.sharePercent.toFixed(0)}%</span>
                  <span className="skeleton-bar" aria-hidden="true">
                    <i style={{ width: `${Math.max(2, row.sharePercent)}%` }} />
                  </span>
                  <span className="skeleton-basis">{row.basis}</span>
                </li>
              ))}
            </ol>
          </details>
        ) : null}

        {developerMode ? (
          <details className="journey-tech-details" data-testid="scene-detail-tech-details">
            <summary>技术详情</summary>
            {isHookPayoffLens(observationLens) && hookResolutionRow ? (
              <HookResolutionEvidenceSection row={hookResolutionRow} />
            ) : null}
            <JourneyInspectorSection title="分数" testId="scene-tech-scores">
              {lensBinding ? (
                <p data-testid="scene-current-lens-score">
                  {formatLensBindingCaption(lensBinding)}
                </p>
              ) : null}
              {node.overall_reading_score != null ? (
                <p data-testid="scene-overall-reading-score">
                  综合阅读分 {Math.round(node.overall_reading_score)}
                </p>
              ) : null}
              {node.composite_role_fit ? (
                <p data-testid="scene-composite-role-fit">
                  角色契合 {node.composite_role_fit}
                </p>
              ) : null}
            </JourneyInspectorSection>
            {node.insight_source ? (
              <JourneyInspectorSection title="洞察来源" testId="scene-tech-insight-source">
                <p>{node.insight_source}</p>
              </JourneyInspectorSection>
            ) : null}
            {node.evidence_paragraph_ids?.length ? (
              <JourneyInspectorSection title="正文证据" testId="scene-tech-evidence">
                <JourneyEvidenceList rows={evidenceRows} onLocateEvidence={onLocateEvidence} />
              </JourneyInspectorSection>
            ) : null}
            {narrative ? (
              <JourneyInspectorSection title="前后承接" testId="scene-tech-bridging">
                <ul data-testid="scene-narrative-list">
                  <li>{narrative.whyHighOrLow}</li>
                  <li>{narrative.priorSetup}</li>
                  <li>{narrative.laterPayoff}</li>
                </ul>
              </JourneyInspectorSection>
            ) : null}
            {(node.primary_diagnosis || node.data_quality_issue) && (
              <JourneyInspectorSection title="诊断" testId="scene-tech-diagnosis">
                {node.primary_diagnosis ? <p>主诊断：{node.primary_diagnosis}</p> : null}
                {node.data_quality_issue ? <p>数据质量：{node.data_quality_issue}</p> : null}
              </JourneyInspectorSection>
            )}
          </details>
        ) : null}

        {onOpenInSceneList ? (
          <button type="button" className="journey-inline-button" onClick={onOpenInSceneList}>
            在场景列表中定位
          </button>
        ) : null}
      </JourneyInspectorBody>
    </JourneyInspectorShell>
  );
}

// "risks" retired: the 阅读阻力 tab reported a derived field (reading_momentum) and its
// penalty arithmetic, which is a statement about the formula rather than about the reader.
// The type kept the member so a stored tab preference does not crash on load.
export type PhaseDetailTab = "overview" | "questions" | "risks" | "scenes";

const PHASE_TABS: { id: PhaseDetailTab; label: string; testId: string }[] = [
  { id: "overview", label: "阶段概览", testId: "phase-detail-tab-overview" },
  { id: "questions", label: "钩子回收", testId: "phase-detail-tab-questions" },
  { id: "scenes", label: "相关场景", testId: "phase-detail-tab-scenes" },
];

type PhaseDetailProps = {
  phase: JourneyPhaseVisualization;
  visualization: ReaderJourneyVisualization;
  onSelectScene: (node: JourneySceneNode) => void;
  onClose?: () => void;
};

function phaseSceneNodes(
  visualization: ReaderJourneyVisualization,
  phase: JourneyPhaseVisualization,
): JourneySceneNode[] {
  return visualization.scene_nodes.filter(
    (node) =>
      node.scene_ordinal >= phase.start_scene_ordinal &&
      node.scene_ordinal <= phase.end_scene_ordinal,
  );
}

function peakSceneInPhase(
  visualization: ReaderJourneyVisualization,
  phase: JourneyPhaseVisualization,
): { scene_ordinal: number; value: number } | null {
  const series = visualization.curve_series.engagement ?? [];
  let best: { scene_ordinal: number; value: number } | null = null;
  for (const point of series) {
    if (
      point.scene_ordinal < phase.start_scene_ordinal ||
      point.scene_ordinal > phase.end_scene_ordinal
    ) {
      continue;
    }
    const value =
      typeof point.value === "number"
        ? point.value
        : typeof point.end === "number"
          ? point.end
          : 0;
    if (!best || value > best.value) {
      best = { scene_ordinal: point.scene_ordinal, value };
    }
  }
  return best;
}

function uniqueQuestions(
  items: Array<{ question?: string } | undefined | null>,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    const q = item?.question?.trim();
    if (!q || seen.has(q)) continue;
    seen.add(q);
    out.push(q);
  }
  return out;
}

export function JourneyPhaseDetailPanel({
  phase,
  visualization,
  onSelectScene,
  onClose,
}: PhaseDetailProps) {
  const [tab, setTab] = useState<PhaseDetailTab>("overview");
  const nodes = useMemo(() => phaseSceneNodes(visualization, phase), [visualization, phase]);
  const peak = useMemo(() => peakSceneInPhase(visualization, phase), [visualization, phase]);

  const createdQs = useMemo(
    () => uniqueQuestions(nodes.flatMap((n) => n.reader_question_created ?? [])),
    [nodes],
  );
  const answeredQs = useMemo(
    () => uniqueQuestions(nodes.flatMap((n) => n.reader_question_answered ?? [])),
    [nodes],
  );
  const inQs = useMemo(() => {
    const first = nodes[0];
    return uniqueQuestions([
      { question: phase.primary_reader_question },
      ...(first?.reader_question_in ?? []),
    ]);
  }, [nodes, phase.primary_reader_question]);
  const openQs = useMemo(() => {
    const last = nodes[nodes.length - 1];
    return uniqueQuestions(last?.reader_question_out ?? []);
  }, [nodes]);

  const overlappingRisks = useMemo(() => {
    const loopRisks = getNarrativeLoopRisks(visualization)
      .filter((risk) => {
        const start = Number(risk.start_scene_ordinal ?? 0);
        const end = Number(risk.end_scene_ordinal ?? start);
        return end >= phase.start_scene_ordinal && start <= phase.end_scene_ordinal;
      })
      .map((risk) => ({
        risk_type: risk.risk_type,
        start_scene_ordinal: Number(risk.start_scene_ordinal ?? phase.start_scene_ordinal),
        end_scene_ordinal: Number(risk.end_scene_ordinal ?? risk.start_scene_ordinal ?? phase.end_scene_ordinal),
        span: Number(risk.span ?? 1),
        summary: formatOpenLoopRiskSummary(risk),
        trigger: risk.loop_id,
        needs_review: risk.risk_type === "narrative_loop_inconsistent",
      }));
    const consistency = getNarrativeLoopConsistency(visualization);
    const legacy = visualization.risk_intervals.filter((interval) => {
      const overlaps =
        interval.end_scene_ordinal >= phase.start_scene_ordinal &&
        interval.start_scene_ordinal <= phase.end_scene_ordinal;
      if (!overlaps) return false;
      if (interval.risk_type === "consecutive_no_payoff" && loopRisks.length) return false;
      if (
        interval.risk_type === "consecutive_no_payoff" &&
        consistency?.status === "inconsistent"
      ) {
        return false;
      }
      return true;
    });
    if (consistency?.status === "inconsistent" && !loopRisks.some((r) => r.risk_type === "narrative_loop_inconsistent")) {
      loopRisks.unshift({
        risk_type: "narrative_loop_inconsistent",
        start_scene_ordinal: phase.start_scene_ordinal,
        end_scene_ordinal: phase.end_scene_ordinal,
        span: Math.max(1, phase.end_scene_ordinal - phase.start_scene_ordinal + 1),
        summary: consistency.user_message || "当前关系识别结果不一致，暂不作为确定结论",
        trigger: "narrative_loop_consistency",
        needs_review: true,
      });
    }
    return [...loopRisks, ...legacy];
  }, [visualization, phase.start_scene_ordinal, phase.end_scene_ordinal]);

  const avgCognitive = useMemo(() => {
    if (!nodes.length) return null;
    const sum = nodes.reduce((acc, n) => acc + Number(n.scores?.cognitive_load ?? 0), 0);
    return Math.round(sum / nodes.length);
  }, [nodes]);

  const engagementDelta = useMemo(() => {
    if (nodes.length < 2) return null;
    const first = Number(nodes[0]?.engagement?.engagement_score ?? 0);
    const last = Number(nodes[nodes.length - 1]?.engagement?.engagement_score ?? 0);
    return last - first;
  }, [nodes]);

  const conclusion = (phase.summary || "").trim();
  const hasQuestionPayoffContent =
    inQs.length > 0 ||
    createdQs.length > 0 ||
    answeredQs.length > 0 ||
    openQs.length > 0 ||
    Boolean(phase.reading_payoff?.trim()) ||
    Boolean(phase.continuation_motivation?.trim());

  const hasRiskContent =
    overlappingRisks.length > 0 || engagementDelta != null || avgCognitive != null;

  return (
    <JourneyInspectorShell
      testId="journey-phase-detail-panel"
      className="journey-phase-detail-panel"
    >
      <JourneyInspectorHeader
        title={formatJourneyPhaseLabel(phase.title)}
        meta={`场景范围：${formatJourneySceneRangeLabel(phase.start_scene_ordinal, phase.end_scene_ordinal)}`}
        onClose={onClose}
        titleTestId="phase-detail-title"
      />

      <JourneyInspectorTabs
        tabs={PHASE_TABS}
        active={tab}
        onChange={(id) => setTab(id as PhaseDetailTab)}
        testId="phase-detail-tabs"
      />

      <JourneyInspectorBody>
        <div className="scene-detail-tab-panel" data-testid={`phase-detail-panel-${tab}`}>
          {tab === "overview" && (
            <div data-testid="phase-detail-overview">
              {conclusion ? (
                <JourneyPrimaryConclusion text={conclusion} testId="phase-primary-conclusion" />
              ) : null}
              <JourneyCompactMetrics
                items={[
                  {
                    key: "avg-engagement",
                    label: "平均牵引",
                    value: Number(phase.average_engagement ?? 0),
                  },
                  {
                    key: "peak-scene",
                    label: peak ? `峰值 ${formatJourneySceneRangeLabel(peak.scene_ordinal)}` : "峰值",
                    value: peak ? Math.round(peak.value) : 0,
                  },
                  {
                    key: "scene-count",
                    label: "场景数",
                    value: nodes.length,
                  },
                ]}
                testId="phase-compact-metrics"
              />
              <JourneyInspectorSection title="场景范围">
                <p>
                  {formatJourneySceneRangeLabel(phase.start_scene_ordinal, phase.end_scene_ordinal)}
                </p>
              </JourneyInspectorSection>
              {resolvePhaseSummaryDisplay(phase.summary, phase.title) ? (
                <JourneyInspectorSection title="结构任务">
                  <p>{resolvePhaseSummaryDisplay(phase.summary, phase.title)}</p>
                </JourneyInspectorSection>
              ) : null}
              {phase.primary_reader_question ? (
                <JourneyInspectorSection title="核心读者问题">
                  <p>{phase.primary_reader_question}</p>
                </JourneyInspectorSection>
              ) : null}
            </div>
          )}

          {tab === "questions" && (
            <div data-testid="phase-detail-questions">
              {!hasQuestionPayoffContent ? (
                <JourneyInspectorEmptyState kind="no-question-chain" testId="empty-phase-questions" />
              ) : (
                <>
                  {inQs.length ? (
                    <JourneyInspectorSection title="进入阶段时的问题">
                      <ul className="phase-detail-list">
                        {inQs.map((q) => (
                          <li key={q}>{q}</li>
                        ))}
                      </ul>
                    </JourneyInspectorSection>
                  ) : null}
                  {createdQs.length ? (
                    <JourneyInspectorSection title="本阶段新建问题">
                      <ul className="phase-detail-list">
                        {createdQs.map((q) => (
                          <li key={q}>{q}</li>
                        ))}
                      </ul>
                    </JourneyInspectorSection>
                  ) : null}
                  {answeredQs.length ? (
                    <JourneyInspectorSection title="已回答或部分回答">
                      <ul className="phase-detail-list">
                        {answeredQs.map((q) => (
                          <li key={q}>{q}</li>
                        ))}
                      </ul>
                    </JourneyInspectorSection>
                  ) : null}
                  {phase.reading_payoff?.trim() ? (
                    <JourneyInspectorSection title="阶段回报">
                      <p>{phase.reading_payoff}</p>
                    </JourneyInspectorSection>
                  ) : null}
                  {openQs.length ? (
                    <JourneyInspectorSection title="留给下一阶段的问题">
                      <ul className="phase-detail-list">
                        {openQs.map((q) => (
                          <li key={q}>{q}</li>
                        ))}
                      </ul>
                    </JourneyInspectorSection>
                  ) : null}
                  {phase.continuation_motivation?.trim() ? (
                    <JourneyInspectorSection title="续读动力">
                      <p>{phase.continuation_motivation}</p>
                    </JourneyInspectorSection>
                  ) : null}
                </>
              )}
            </div>
          )}

          {tab === "risks" && (
            <div data-testid="phase-detail-risks">
              {!hasRiskContent ? (
                <JourneyInspectorEmptyState kind="no-risk" testId="empty-phase-risks" />
              ) : (
                <>
                  {engagementDelta != null ? (
                    <JourneyInspectorSection title="engagement 变化">
                      <p>
                        {engagementDelta > 0 ? `+${engagementDelta}` : String(engagementDelta)}
                      </p>
                    </JourneyInspectorSection>
                  ) : null}
                  {avgCognitive != null ? (
                    <JourneyInspectorSection title="认知负担">
                      <p>{avgCognitive}</p>
                    </JourneyInspectorSection>
                  ) : null}
                  {overlappingRisks.length ? (
                    <JourneyInspectorSection title="阅读阻力区间">
                      <ul className="phase-detail-list" data-testid="phase-detail-risk-list">
                        {overlappingRisks.map((interval) => (
                          <li
                            key={`${interval.risk_type}-${interval.start_scene_ordinal}`}
                            data-risk-type={interval.risk_type}
                          >
                            <b>{formatJourneyRiskTypeLabel(interval.risk_type)}</b>
                            <span>
                              {" "}
                              {formatJourneySceneRangeLabel(
                                interval.start_scene_ordinal,
                                interval.end_scene_ordinal,
                              )}
                            </span>
                            <p>
                              {formatJourneyRiskSummary({
                                risk_type: interval.risk_type,
                                summary: interval.summary,
                                start_scene_ordinal: interval.start_scene_ordinal,
                                end_scene_ordinal: interval.end_scene_ordinal,
                                span: interval.span,
                              })}
                            </p>
                            <details className="journey-tech-details">
                              <summary>技术详情</summary>
                              <code>{interval.risk_type}</code>
                              {interval.trigger ? <p>{interval.trigger}</p> : null}
                            </details>
                          </li>
                        ))}
                      </ul>
                    </JourneyInspectorSection>
                  ) : (
                    <JourneyInspectorEmptyState kind="no-risk" testId="empty-phase-risk-list" />
                  )}
                </>
              )}
            </div>
          )}

          {tab === "scenes" && (
            <div data-testid="phase-detail-scenes">
              <JourneyRelatedObjectList
                testId="phase-related-scenes"
                items={nodes.map((node) => ({
                  key: String(node.scene_ordinal),
                  primary: `${formatJourneySceneLabel(node.scene_ordinal)} · ${roleLabelZh(node.final_level ?? node.role)}`,
                  secondary: node.scene_value_summary || undefined,
                  meta: `牵引 ${Number(node.engagement?.engagement_score ?? 0)}`,
                  onClick: () => onSelectScene(node),
                  testId: `phase-related-scene-${node.scene_ordinal}`,
                }))}
              />
            </div>
          )}
        </div>
      </JourneyInspectorBody>
    </JourneyInspectorShell>
  );
}

type QuestionInspectorProps = {
  cluster: JourneyQuestionCluster;
  nodes: JourneySceneNode[];
  onSelectScene: (node: JourneySceneNode) => void;
  onClose?: () => void;
};

export function JourneyQuestionInspectorPanel({
  cluster,
  nodes,
  onSelectScene,
  onClose,
}: QuestionInspectorProps) {
  const primary =
    (cluster.primary_question || cluster.cluster_title || "").trim() ||
    cluster.members[0]?.question ||
    "";
  const hasLifecycle = cluster.members.some((m) => m.status || m.created_scene != null);

  return (
    <JourneyInspectorShell
      testId="journey-question-inspector"
      className="journey-inspector-panel"
    >
      <JourneyInspectorHeader
        title={cluster.cluster_title || "问题链"}
        meta={`问题链 · S${cluster.created_scene}`}
        pills={cluster.members[0]?.status ? [questionLifecycleZh(cluster.members[0].status)] : []}
        onClose={onClose}
        titleTestId="question-inspector-title"
      />
      <JourneyInspectorBody>
        {primary ? <JourneyPrimaryConclusion text={primary} /> : null}
        <JourneyInspectorSection title="生命周期状态">
          {!hasLifecycle ? (
            <JourneyInspectorEmptyState kind="no-lifecycle" testId="empty-question-lifecycle" />
          ) : (
            <ul className="phase-detail-list">
              {cluster.members.map((member) => {
                const memberNode = nodes.find((n) => n.scene_ordinal === member.created_scene);
                return (
                  <li key={member.chain_id}>
                    <button
                      type="button"
                      className="journey-inline-button"
                      disabled={!memberNode}
                      onClick={() => memberNode && onSelectScene(memberNode)}
                    >
                      {member.question}
                      <small>
                        {" "}
                        · S{member.created_scene} · {questionLifecycleZh(member.status)}
                      </small>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </JourneyInspectorSection>
        <JourneyInspectorSection title="首次提出位置">
          <p>Scene {cluster.created_scene}</p>
        </JourneyInspectorSection>
      </JourneyInspectorBody>
    </JourneyInspectorShell>
  );
}

type MarkerInspectorProps = {
  kind: "hook" | "payoff";
  node: JourneySceneNode | null;
  riskInterval?: JourneyRiskInterval | null;
  onLocateEvidence?: (paragraphId: string) => void;
  onClose?: () => void;
};

export function JourneyMarkerInspectorPanel({
  kind,
  node,
  riskInterval,
  onLocateEvidence,
  onClose,
}: MarkerInspectorProps) {
  const hook = node?.primary_hook ?? node?.hooks?.[0] ?? null;
  const payoff = node?.primary_payoff ?? node?.payoffs?.[0] ?? null;

  if (kind === "hook") {
    const summary = (hook?.summary || "").trim();
    const evidenceId = hook?.evidence_paragraph_ids?.[0];
    return (
      <JourneyInspectorShell testId="journey-hook-inspector" className="journey-inspector-panel">
        <JourneyInspectorHeader
          title={summary || "悬念详情"}
          meta={node ? formatJourneySceneLabel(node.scene_ordinal) : "悬念"}
          pills={hook?.type ? [hookTypeZh(hook.type)] : []}
          onClose={onClose}
          locateLabel={evidenceId && onLocateEvidence ? "定位正文" : undefined}
          onLocate={
            evidenceId && onLocateEvidence ? () => onLocateEvidence(evidenceId) : undefined
          }
        />
        <JourneyInspectorBody>
          {summary ? (
            <JourneyInspectorSection title="发生了什么">
              <JourneyPrimaryConclusion text={summary} />
            </JourneyInspectorSection>
          ) : null}
          {node ? (
            <>
              <JourneyInspectorSection title="为什么形成悬念">
                <p>{hook?.gap || hookTypeZh(hook?.type) || "本场提出了读者想继续确认的问题。"}</p>
              </JourneyInspectorSection>
              <JourneyInspectorSection title="读者正在等待什么">
                <p>读者想知道后续会如何回应。</p>
              </JourneyInspectorSection>
              {evidenceId && onLocateEvidence ? (
                <JourneyInspectorSection title="正文证据">
                  <JourneyEvidenceList
                    rows={[
                      {
                        paragraphId: evidenceId,
                        conclusion: summary || "悬念",
                        kind: "hook",
                      },
                    ]}
                    onLocateEvidence={onLocateEvidence}
                  />
                </JourneyInspectorSection>
              ) : null}
            </>
          ) : (
            <JourneyInspectorEmptyState kind="no-selection" testId="empty-hook-node" />
          )}
        </JourneyInspectorBody>
      </JourneyInspectorShell>
    );
  }

  const summary = (payoff?.summary || "").trim();
  const evidenceId = payoff?.evidence_paragraph_ids?.[0];
  return (
    <JourneyInspectorShell testId="journey-payoff-inspector" className="journey-inspector-panel">
      <JourneyInspectorHeader
        title={summary || "回应详情"}
        meta={node ? formatJourneySceneLabel(node.scene_ordinal) : "回应"}
        pills={payoff?.type ? [payoffTypeZh(payoff.type)] : []}
        onClose={onClose}
        locateLabel={evidenceId && onLocateEvidence ? "定位正文" : undefined}
        onLocate={
          evidenceId && onLocateEvidence ? () => onLocateEvidence(evidenceId) : undefined
        }
      />
      <JourneyInspectorBody>
        <JourneyInspectorSection title="回应了什么">
          {summary ? <JourneyPrimaryConclusion text={summary} /> : <p>尚未识别出明确回应摘要。</p>}
        </JourneyInspectorSection>
        {node && evidenceId && onLocateEvidence ? (
          <JourneyInspectorSection title="原悬念和当前回应证据">
            <JourneyEvidenceList
              rows={[
                {
                  paragraphId: evidenceId,
                  conclusion: summary || "回应",
                  kind: "payoff",
                },
              ]}
              onLocateEvidence={onLocateEvidence}
            />
          </JourneyInspectorSection>
        ) : null}
      </JourneyInspectorBody>
    </JourneyInspectorShell>
  );
}
