import { useEffect, useMemo, useState } from "react";
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
  METRIC_LABELS_ZH,
  payoffTypeZh,
  questionLifecycleZh,
  resolvePhaseSummaryDisplay,
  roleLabelZh,
  SCORE_TOOLTIPS_ZH,
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
import {
  HookList,
  PayoffList,
  ReaderQuestionList,
  TechniqueList,
  WritingTakeawayList,
  normalizeWritingTakeawayList,
} from "./sceneDetailFields";
import { buildSceneNarrative } from "./journeySceneNarrative";
import type { ObservationLensId } from "./observationLenses";
import { DEFAULT_OBSERVATION_LENS } from "./observationLenses";
import {
  getQuestionLifecycle,
  hookPayoffCombinationExplanation,
  isHookPayoffLens,
  lifecycleStatusLabelZh,
  otherDiagnosesForHookPayoffLens,
  questionsForScene,
  sceneRoleInLifecycle,
} from "./hookPayoffLensModel";
import { primaryBandLabelForScene } from "./diagnosisBandModel";
import type { SceneDiagnosisLike } from "./diagnosisBandModel";
import {
  formatPayoffClaimLabel,
  formatHookHandoffFromLoops,
  formatOpenLoopRiskSummary,
  getNarrativeLoopConsistency,
  getNarrativeLoopRisks,
  getNarrativeLoops,
  getScenePayoffClaim,
} from "./narrativeLoopView";
import { isTautologyContinueDrive } from "./readerJourneyLensExplanation";
import {
  formatLensBindingCaption,
  resolveLensMetricBinding,
  readingMomentumLabelZh,
} from "./lensMetricBinding";

export type SceneDetailTab =
  | "overview"
  | "questions"
  | "payoffs"
  | "techniques"
  | "evidence";

const TABS: { id: SceneDetailTab; label: string; testId: string }[] = [
  { id: "overview", label: "概览", testId: "scene-detail-tab-overview" },
  { id: "questions", label: "问题链", testId: "scene-detail-tab-questions" },
  { id: "payoffs", label: "回报与钩子", testId: "scene-detail-tab-payoffs" },
  { id: "techniques", label: "写作技法", testId: "scene-detail-tab-techniques" },
  { id: "evidence", label: "证据", testId: "scene-detail-tab-evidence" },
];

const CORE_SCORE_KEYS = ["reading_momentum", "curiosity", "tension"] as const;

type Props = {
  node: JourneySceneNode;
  onLocateEvidence: (paragraphId: string) => void;
  onClose?: () => void;
  onOpenInSceneList?: () => void;
  visualization?: ReaderJourneyVisualization | null;
  observationLensLabel?: string | null;
  observationLens?: ObservationLensId | null;
};

function scoreValue(node: JourneySceneNode, key: (typeof CORE_SCORE_KEYS)[number]): number {
  if (key === "reading_momentum") {
    return Number(
      node.scores?.reading_momentum ?? node.engagement?.engagement_score ?? 0,
    );
  }
  return Number(node.scores?.[key] ?? 0);
}

function hasQuestionItems(items: unknown): boolean {
  return Array.isArray(items) && items.length > 0;
}

export function JourneySceneDetailPanel({
  node,
  onLocateEvidence,
  onClose,
  onOpenInSceneList,
  visualization = null,
  observationLensLabel = null,
  observationLens = DEFAULT_OBSERVATION_LENS,
}: Props) {
  const [tab, setTab] = useState<SceneDetailTab>("overview");

  useEffect(() => {
    // Keep tab across Scene switches.
  }, [node.scene_ordinal]);

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
      push(p.evidence_paragraph_ids, p.summary ?? "回报", "payoff");
    }
    for (const h of node.hooks ?? []) {
      push(h.evidence_paragraph_ids, h.summary ?? "钩子", "hook");
    }
    if (node.primary_hook) {
      push(node.primary_hook.evidence_paragraph_ids, node.primary_hook.summary ?? "主钩子", "hook");
    }
    for (const t of node.techniques ?? []) {
      push(t.evidence_paragraph_ids, t.name ?? "技法", "technique");
    }
    for (const r of node.risk_points ?? []) {
      push(r.evidence_paragraph_ids, r.summary ?? "流失风险", "risk");
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

  const hasQuestions =
    (node.reader_question_in?.length ?? 0) +
      (node.reader_question_created?.length ?? 0) +
      (node.reader_question_answered?.length ?? 0) +
      (node.reader_question_out?.length ?? 0) >
    0;

  const hasPayoffs = (node.payoffs?.length ?? 0) > 0 || !!node.primary_payoff;
  const hasHooks = (node.hooks?.length ?? 0) > 0 || !!node.primary_hook;
  const takeaways = normalizeWritingTakeawayList(node.writing_takeaways);
  const hasTechniques = (node.techniques?.length ?? 0) > 0 || takeaways.length > 0;
  const riskText = node.primary_risk?.summary || node.risk_points?.[0]?.summary || "";
  const conclusion = (node.scene_value_summary || "").trim();
  const role = roleLabelZh(node.final_level ?? node.role);

  const coreMetrics = CORE_SCORE_KEYS.map((key) => ({
    key,
    label:
      key === "reading_momentum"
        ? visualization
          ? readingMomentumLabelZh(visualization)
          : "阅读动力"
        : METRIC_LABELS_ZH[key as keyof typeof METRIC_LABELS_ZH] ?? key,
    value: Math.max(0, Math.min(100, scoreValue(node, key))),
    title:
      key === "reading_momentum"
        ? "综合阅读动力（reading_momentum）"
        : SCORE_TOOLTIPS_ZH[key],
  }));

  return (
    <JourneyInspectorShell
      testId="journey-detail-drawer"
      className="journey-scene-detail-panel"
    >
      <JourneyInspectorHeader
        title={`${formatJourneySceneLabel(node.scene_ordinal)} · ${role}`}
        meta={`场景范围：${formatJourneySceneRangeLabel(node.scene_ordinal)}`}
        pills={[role]}
        onClose={onClose}
        titleTestId="scene-detail-title"
      />

      <JourneyInspectorTabs
        tabs={TABS}
        active={tab}
        onChange={(id) => setTab(id as SceneDetailTab)}
        testId="scene-detail-tabs"
      />

      <JourneyInspectorBody>
        <div className="scene-detail-tab-panel" data-testid={`scene-detail-panel-${tab}`}>
          {tab === "overview" && (
            <div data-testid="scene-detail-overview">
              {conclusion ? (
                <JourneyPrimaryConclusion text={conclusion} testId="scene-primary-conclusion" />
              ) : null}
              <JourneyInspectorSection title="场景概览" testId="scene-overview-level">
                <p>{role}</p>
                {node.node_type || node.scene_role ? (
                  <p data-testid="scene-overview-v2-meta">
                    {node.node_type ? `节点类型：${node.node_type}` : null}
                    {node.node_type && node.scene_role ? " · " : null}
                    {node.scene_role ? `场景角色：${node.scene_role}` : null}
                  </p>
                ) : null}
              </JourneyInspectorSection>
              {(node.primary_diagnosis || node.positive_mechanism || node.data_quality_issue) && (
                <JourneyInspectorSection title="诊断" testId="scene-overview-diagnosis">
                  <p data-testid="scene-primary-diagnosis">
                    主诊断：
                    {primaryBandLabelForScene({
                      scene_ordinal: node.scene_ordinal,
                      primary_diagnosis: node.primary_diagnosis,
                      secondary_diagnoses: node.secondary_diagnoses,
                      positive_mechanism: node.positive_mechanism,
                      data_quality_issue: node.data_quality_issue,
                    })}
                  </p>
                  {node.secondary_diagnoses?.length ? (
                    <p data-testid="scene-secondary-diagnoses">
                      次要：{node.secondary_diagnoses.join(" · ")}
                    </p>
                  ) : null}
                  {node.positive_mechanism ? (
                    <p data-testid="scene-positive-mechanism">
                      正向机制：{node.positive_mechanism}
                    </p>
                  ) : null}
                  {node.data_quality_issue ? (
                    <p data-testid="scene-data-quality-issue">
                      数据质量：{node.data_quality_issue}
                    </p>
                  ) : null}
                  <p>置信度：{Math.round((node.confidence ?? 0) * 100)}%</p>
                </JourneyInspectorSection>
              )}
              {visualization ? (
                <JourneyInspectorSection title="高低点叙事" testId="scene-overview-narrative">
                  {(() => {
                    const narrative = buildSceneNarrative(visualization, node);
                    return (
                      <ul data-testid="scene-narrative-list">
                        <li>{narrative.whyHighOrLow}</li>
                        <li>{narrative.narrativeTechnique}</li>
                        <li>{narrative.priorSetup}</li>
                        <li>{narrative.laterPayoff}</li>
                      </ul>
                    );
                  })()}
                  {observationLensLabel && visualization ? (
                    <p data-testid="scene-current-lens-score">
                      当前镜头：{observationLensLabel}
                      {" · "}
                      {formatLensBindingCaption(
                        resolveLensMetricBinding(
                          visualization,
                          observationLens ?? DEFAULT_OBSERVATION_LENS,
                          node,
                        ),
                      )}
                    </p>
                  ) : null}
                </JourneyInspectorSection>
              ) : null}
              {node.phase_ordinal != null ? (
                <JourneyInspectorSection title="所属阶段" testId="scene-overview-phase">
                  <p>阶段 {node.phase_ordinal}</p>
                </JourneyInspectorSection>
              ) : null}
              {node.dominant_emotion ? (
                <JourneyInspectorSection title="主要情绪" testId="scene-overview-emotion">
                  <p>{node.dominant_emotion}</p>
                </JourneyInspectorSection>
              ) : null}
              <JourneyInspectorSection title="关键指标" testId="scene-overview-metrics">
                <JourneyCompactMetrics items={coreMetrics} testId="scene-detail-score-bars" />
              </JourneyInspectorSection>
              {riskText ? (
                <JourneyInspectorSection title="核心流失风险" testId="scene-overview-risk">
                  <p>{riskText}</p>
                </JourneyInspectorSection>
              ) : null}
              <JourneyInspectorSection title="写作建议" testId="scene-overview-takeaways">
                {takeaways.length ? (
                  <WritingTakeawayList items={node.writing_takeaways} />
                ) : (
                  <JourneyInspectorEmptyState kind="no-section" testId="empty-overview-takeaways" />
                )}
              </JourneyInspectorSection>
            </div>
          )}

          {tab === "questions" && (
            <div className="scene-detail-lifecycle" data-testid="scene-detail-questions">
              {!hasQuestions ? (
                <JourneyInspectorEmptyState
                  kind="no-question-chain"
                  testId="empty-questions"
                  actionLabel="查看场景概览"
                  onAction={() => setTab("overview")}
                />
              ) : (
                <>
                  {hasQuestionItems(node.reader_question_created) ? (
                    <JourneyInspectorSection title="本场景建立的问题">
                      <ReaderQuestionList
                        items={node.reader_question_created}
                        onLocateEvidence={onLocateEvidence}
                      />
                    </JourneyInspectorSection>
                  ) : null}
                  {hasQuestionItems(node.reader_question_in) ? (
                    <JourneyInspectorSection title="延续的问题">
                      <ReaderQuestionList
                        items={node.reader_question_in}
                        onLocateEvidence={onLocateEvidence}
                      />
                    </JourneyInspectorSection>
                  ) : null}
                  {hasQuestionItems(node.reader_question_answered) ? (
                    <JourneyInspectorSection title="回答 / 转化的问题">
                      <ReaderQuestionList
                        items={node.reader_question_answered}
                        onLocateEvidence={onLocateEvidence}
                      />
                    </JourneyInspectorSection>
                  ) : null}
                  {hasQuestionItems(node.reader_question_out) ? (
                    <JourneyInspectorSection title="留给后续的问题">
                      <ReaderQuestionList
                        items={node.reader_question_out}
                        onLocateEvidence={onLocateEvidence}
                      />
                    </JourneyInspectorSection>
                  ) : null}
                </>
              )}
            </div>
          )}

          {tab === "payoffs" && (
            <div data-testid="scene-detail-payoffs">
              {visualization && isHookPayoffLens(observationLens) ? (
                <HookPayoffLifecycleSection
                  visualization={visualization}
                  node={node}
                />
              ) : null}
              {!hasPayoffs && !hasHooks && !(visualization && isHookPayoffLens(observationLens)) ? (
                <JourneyInspectorEmptyState
                  kind="no-hook-payoff"
                  testId="empty-hook-payoff"
                  actionLabel="查看场景概览"
                  onAction={() => setTab("overview")}
                />
              ) : (
                <>
                  {hasHooks ? (
                    <JourneyInspectorSection title="钩子" testId="scene-hooks-section">
                      {(node.hooks?.length ?? 0) > 0 ? (
                        <HookList items={node.hooks} onLocateEvidence={onLocateEvidence} />
                      ) : null}
                      {node.primary_hook ? (
                        <div className="journey-hook-flat" data-testid="primary-hook-grid">
                          <p>
                            <b>{hookTypeZh(node.primary_hook.type)}</b>
                            {node.primary_hook.summary ? ` · ${node.primary_hook.summary}` : ""}
                          </p>
                          {node.primary_hook.known ? <p>已知：{node.primary_hook.known}</p> : null}
                          {node.primary_hook.gap ? <p>缺口：{node.primary_hook.gap}</p> : null}
                          {node.primary_hook.continue_drive &&
                          !isTautologyContinueDrive(node.primary_hook.continue_drive) ? (
                            <p>继续动力：{node.primary_hook.continue_drive}</p>
                          ) : null}
                          {node.primary_hook.next_handoff ? (
                            <p>下一场承接：{node.primary_hook.next_handoff}</p>
                          ) : visualization ? (
                            (() => {
                              const handoff = formatHookHandoffFromLoops(
                                getNarrativeLoops(visualization),
                                node.scene_ordinal,
                              );
                              if (handoff.text) {
                                return <p>下一场承接：{handoff.text}</p>;
                              }
                              return (
                                <p className="journey-inspector-hint">
                                  {handoff.hint || "当前钩子尚未识别出明确的后续承接。"}
                                </p>
                              );
                            })()
                          ) : (
                            <p className="journey-inspector-hint">
                              当前钩子尚未识别出明确的后续承接。
                            </p>
                          )}
                        </div>
                      ) : null}
                    </JourneyInspectorSection>
                  ) : null}
                  {hasPayoffs ? (
                    <JourneyInspectorSection title="回报" testId="scene-payoffs-section">
                      {(node.payoffs?.length ?? 0) > 0 ? (
                        <PayoffList items={node.payoffs} onLocateEvidence={onLocateEvidence} />
                      ) : node.primary_payoff ? (
                        <article data-testid="primary-payoff-card">
                          <b>{payoffTypeZh(node.primary_payoff.type)}</b>
                          <p>{node.primary_payoff.summary || "—"}</p>
                          {node.primary_payoff.strength != null ? (
                            <small>本场强度 {node.primary_payoff.strength}</small>
                          ) : null}
                        </article>
                      ) : null}
                    </JourneyInspectorSection>
                  ) : null}
                </>
              )}
            </div>
          )}

          {tab === "techniques" && (
            <div data-testid="scene-detail-techniques">
              {!hasTechniques ? (
                <JourneyInspectorEmptyState kind="no-technique" testId="empty-techniques" />
              ) : (
                <>
                  {(node.techniques?.length ?? 0) > 0 ? (
                    <JourneyInspectorSection title="技法">
                      <TechniqueList items={node.techniques} onLocateEvidence={onLocateEvidence} />
                    </JourneyInspectorSection>
                  ) : null}
                  {takeaways.length > 0 ? (
                    <JourneyInspectorSection title="写作启示">
                      <WritingTakeawayList items={node.writing_takeaways} />
                    </JourneyInspectorSection>
                  ) : null}
                </>
              )}
            </div>
          )}

          {tab === "evidence" && (
            <div data-testid="scene-detail-evidence">
              <JourneyEvidenceList rows={evidenceRows} onLocateEvidence={onLocateEvidence} />
            </div>
          )}
        </div>

        {onOpenInSceneList ? (
          <button type="button" className="journey-inline-button" onClick={onOpenInSceneList}>
            在场景列表中定位
          </button>
        ) : null}
      </JourneyInspectorBody>
    </JourneyInspectorShell>
  );
}

function HookPayoffLifecycleSection({
  visualization,
  node,
}: {
  visualization: ReaderJourneyVisualization;
  node: JourneySceneNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const lifecycle = getQuestionLifecycle(visualization);
  const related = questionsForScene(lifecycle, node.scene_ordinal);
  const primary = related[0];
  const others = related.slice(1);
  const hook = typeof node.scores?.hook === "number" ? node.scores.hook : null;
  const payoff = typeof node.scores?.payoff === "number" ? node.scores.payoff : null;
  const combo = hookPayoffCombinationExplanation(hook, payoff);
  const diagLike: SceneDiagnosisLike = {
    scene_ordinal: node.scene_ordinal,
    primary_diagnosis: node.primary_diagnosis,
    secondary_diagnoses: node.secondary_diagnoses,
    positive_mechanism: node.positive_mechanism,
    role: node.role,
    node_type: node.node_type,
    include_in_main_curve: node.include_in_main_curve,
  };
  const otherDiag = otherDiagnosesForHookPayoffLens(diagLike);

  return (
    <>
      <JourneyInspectorSection title="钩子与回报解读" testId="scene-hook-payoff-combo">
        <p data-testid="scene-hook-payoff-combo-text">{combo}</p>
        <p className="journey-inspector-hint" data-testid="scene-payoff-plain">
          {formatPayoffClaimLabel(getScenePayoffClaim(visualization, node.scene_ordinal), payoff)}
        </p>
      </JourneyInspectorSection>
      <JourneyInspectorSection title="问题生命周期" testId="scene-question-lifecycle">
        {!related.length ? (
          <p data-testid="scene-question-lifecycle-empty">
            本场未关联到明确的问题生命周期。
          </p>
        ) : (
          <>
            {primary ? (
              <article
                className="journey-lifecycle-card"
                data-testid={`scene-lifecycle-${primary.question_id}`}
              >
                <p>
                  <b>
                    {primary.question_id}：{primary.question_text}
                  </b>
                </p>
                <p>
                  S{primary.setup_scene} 建立问题
                  {(primary.development_scenes || []).map((s) => ` → S${s} 推进`).join("")}
                  {primary.payoff_scene != null
                    ? ` → S${primary.payoff_scene} ${
                        primary.status === "paid_off" ? "完成兑现" : "部分兑现"
                      }`
                    : ""}
                </p>
                <p>当前状态：{lifecycleStatusLabelZh(primary.status)}</p>
                <p>
                  本场作用：{sceneRoleInLifecycle(primary, node.scene_ordinal)}
                </p>
                {typeof primary.strength === "number" ? (
                  <p>confidence / strength：{primary.strength}</p>
                ) : null}
              </article>
            ) : null}
            {others.length > 0 ? (
              <details
                open={expanded}
                onToggle={(e) => setExpanded((e.target as HTMLDetailsElement).open)}
                data-testid="scene-lifecycle-others"
              >
                <summary>其他关联问题（{others.length}）</summary>
                {others.map((item) => (
                  <article key={item.question_id} className="journey-lifecycle-card">
                    <p>
                      <b>
                        {item.question_id}：{item.question_text}
                      </b>
                    </p>
                    <p>
                      建立 S{item.setup_scene}
                      {item.payoff_scene != null ? ` · 兑现 S${item.payoff_scene}` : ""}
                      {" · "}
                      {lifecycleStatusLabelZh(item.status)}
                      {" · 本场："}
                      {sceneRoleInLifecycle(item, node.scene_ordinal)}
                    </p>
                  </article>
                ))}
              </details>
            ) : null}
          </>
        )}
      </JourneyInspectorSection>
      {otherDiag.length > 0 ? (
        <JourneyInspectorSection title="其他诊断" testId="scene-other-diagnoses">
          <p>{otherDiag.join(" · ")}</p>
          <p className="journey-inspector-hint">
            主诊断标签：{primaryBandLabelForScene(diagLike)}（非钩子回报主标签时收纳于此）
          </p>
        </JourneyInspectorSection>
      ) : null}
    </>
  );
}

export type PhaseDetailTab = "overview" | "questions" | "risks" | "scenes";

const PHASE_TABS: { id: PhaseDetailTab; label: string; testId: string }[] = [
  { id: "overview", label: "阶段概览", testId: "phase-detail-tab-overview" },
  { id: "questions", label: "问题与回报", testId: "phase-detail-tab-questions" },
  { id: "risks", label: "流失风险", testId: "phase-detail-tab-risks" },
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
      // Prefer NarrativeLoopView open-loop risks over score/empty-array consecutive_no_payoff.
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
                    <JourneyInspectorSection title="流失风险区间">
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
  kind: "hook" | "payoff" | "risk";
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

  if (kind === "risk") {
    const summary = formatJourneyRiskSummary({
      risk_type: riskInterval?.risk_type,
      summary: riskInterval?.summary || riskInterval?.trigger,
      start_scene_ordinal: riskInterval?.start_scene_ordinal,
      end_scene_ordinal: riskInterval?.end_scene_ordinal,
      span: riskInterval?.span,
    });
    return (
      <JourneyInspectorShell testId="journey-risk-inspector" className="journey-inspector-panel">
        <JourneyInspectorHeader
          title="流失风险"
          meta={
            riskInterval
              ? `场景 ${riskInterval.start_scene_ordinal}—${riskInterval.end_scene_ordinal}`
              : "流失风险"
          }
          pills={
            riskInterval?.risk_type
              ? [formatJourneyRiskTypeLabel(riskInterval.risk_type)]
              : []
          }
          onClose={onClose}
        />
        <JourneyInspectorBody>
          {summary ? <JourneyPrimaryConclusion text={summary} /> : null}
          {riskInterval ? (
            <>
              <JourneyInspectorSection title="影响区间">
                <p>
                  场景 {riskInterval.start_scene_ordinal}—{riskInterval.end_scene_ordinal}
                </p>
              </JourneyInspectorSection>
              {riskInterval.trigger ? (
                <JourneyInspectorSection title="流失风险依据">
                  <p>{riskInterval.trigger}</p>
                </JourneyInspectorSection>
              ) : null}
              {riskInterval.field_used ? (
                <JourneyInspectorSection title="使用的字段">
                  <p data-testid="risk-field-used">{riskInterval.field_used}</p>
                </JourneyInspectorSection>
              ) : null}
              <JourneyInspectorSection title="实际 Scene 范围">
                <p data-testid="risk-scene-range">
                  S{riskInterval.start_scene_ordinal}—S{riskInterval.end_scene_ordinal}
                  {typeof riskInterval.span === "number" ? `（跨度 ${riskInterval.span}）` : ""}
                </p>
              </JourneyInspectorSection>
              {riskInterval.penalties?.length ? (
                <JourneyInspectorSection title="附加惩罚">
                  <ul data-testid="risk-penalties">
                    {riskInterval.penalties.map((penalty) => (
                      <li key={`${penalty.code}-${penalty.amount}`}>
                        {penalty.label ?? penalty.code}：+{penalty.amount}
                      </li>
                    ))}
                  </ul>
                </JourneyInspectorSection>
              ) : null}
              {typeof riskInterval.final_risk === "number" ? (
                <JourneyInspectorSection title="最终风险值">
                  <p data-testid="risk-final-value">{Math.round(riskInterval.final_risk)}</p>
                </JourneyInspectorSection>
              ) : null}
              <JourneyInspectorSection title="可能影响">
                <p>
                  阅读动力偏低、连续下降或高钩子未兑现，可能降低读者继续阅读的意愿。属于提示性判断，并非确定性失败。
                </p>
              </JourneyInspectorSection>
              <details className="journey-tech-details">
                <summary>技术详情</summary>
                <code>{riskInterval.risk_type}</code>
              </details>
            </>
          ) : (
            <JourneyInspectorEmptyState kind="no-risk" testId="empty-risk" />
          )}
        </JourneyInspectorBody>
      </JourneyInspectorShell>
    );
  }

  if (kind === "hook") {
    const summary = (hook?.summary || "").trim();
    const evidenceId = hook?.evidence_paragraph_ids?.[0];
    return (
      <JourneyInspectorShell testId="journey-hook-inspector" className="journey-inspector-panel">
        <JourneyInspectorHeader
          title={summary || "Hook 详情"}
          meta={node ? `Hook · Scene ${node.scene_ordinal}` : "Hook"}
          pills={hook?.type ? [hookTypeZh(hook.type)] : []}
          onClose={onClose}
          locateLabel={evidenceId && onLocateEvidence ? "定位正文" : undefined}
          onLocate={
            evidenceId && onLocateEvidence ? () => onLocateEvidence(evidenceId) : undefined
          }
        />
        <JourneyInspectorBody>
          {summary ? <JourneyPrimaryConclusion text={summary} /> : null}
          {node ? (
            <>
              <JourneyInspectorSection title="所属 Scene">
                <p>Scene {node.scene_ordinal}</p>
              </JourneyInspectorSection>
              {hook?.type ? (
                <JourneyInspectorSection title="钩子类型">
                  <p>{hookTypeZh(hook.type)}</p>
                </JourneyInspectorSection>
              ) : null}
              {hook?.continue_drive && !isTautologyContinueDrive(hook.continue_drive) ? (
                <JourneyInspectorSection title="预期读者反应">
                  <p>{hook.continue_drive}</p>
                </JourneyInspectorSection>
              ) : null}
              {hook?.next_handoff ? (
                <JourneyInspectorSection title="后续承接">
                  <p>{hook.next_handoff}</p>
                </JourneyInspectorSection>
              ) : (
                <JourneyInspectorEmptyState kind="no-section" testId="empty-hook-followup" />
              )}
              {evidenceId && onLocateEvidence ? (
                <JourneyInspectorSection title="正文证据">
                  <JourneyEvidenceList
                    rows={[
                      {
                        paragraphId: evidenceId,
                        conclusion: summary || "钩子",
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

  // payoff
  const summary = (payoff?.summary || "").trim();
  return (
    <JourneyInspectorShell testId="journey-payoff-inspector" className="journey-inspector-panel">
      <JourneyInspectorHeader
        title={summary || "Payoff 详情"}
        meta={node ? `Payoff · Scene ${node.scene_ordinal}` : "Payoff"}
        pills={payoff?.type ? [payoffTypeZh(payoff.type)] : []}
        onClose={onClose}
      />
      <JourneyInspectorBody>
        {summary ? <JourneyPrimaryConclusion text={summary} /> : null}
        {node ? (
          <>
            <JourneyInspectorSection title="所属 Scene">
              <p>Scene {node.scene_ordinal}</p>
            </JourneyInspectorSection>
            {payoff?.strength != null ? (
              <JourneyInspectorSection title="回报强度">
                <p>{payoff.strength}</p>
              </JourneyInspectorSection>
            ) : null}
            <JourneyInspectorSection title="前置 Hook">
              <p className="journey-inspector-hint" data-testid="empty-payoff-hook">
                当前回报未关联到明确的前置 Hook。
              </p>
            </JourneyInspectorSection>
          </>
        ) : (
          <JourneyInspectorEmptyState kind="no-selection" testId="empty-payoff-node" />
        )}
      </JourneyInspectorBody>
    </JourneyInspectorShell>
  );
}
