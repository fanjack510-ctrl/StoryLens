/**
 * Unified NarrativeLoopView — presentation adapter over Reader Journey visualization.
 * Does not retune weights, formulas, or persisted artifacts.
 */

import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";

export const INCONSISTENT_USER_MESSAGE = "当前关系识别结果不一致，暂不作为确定结论";
export const HARD_BLOCK_USER_MESSAGE = "当前关系识别存在严重冲突，暂不作为确定结论。";
export const SOFT_CONFLICT_USER_MESSAGE =
  "系统找到较可信的承接，但部分分析结果仍存在分歧。";

export type NarrativeLoopStatus =
  | "open"
  | "partially_resolved"
  | "resolved"
  | "transformed"
  | "abandoned"
  | "inconsistent";

export type NarrativePayoffType =
  | "partial"
  | "full"
  | "reversal"
  | "transformed_question"
  | "score_inferred";

export type RelationGrade = "confirmed" | "probable" | "candidate" | "unsupported";

export type NarrativeRelationAssessment = {
  loop_id: string;
  grade: RelationGrade;
  total_score: number;
  blocked?: boolean;
  block_level?: string;
  label_zh?: string;
  grade_label_zh?: string;
  dimensions?: Record<string, { score: number; reason: string }>;
  reasons?: string[];
  conflicts?: NarrativeLoopConflict[];
  is_primary?: boolean;
  payoff_ref?: {
    scene_ordinal?: number;
    type?: string;
    summary?: string;
    source_type?: string;
    evidence_paragraph_ids?: string[];
  };
  hook_ref?: {
    scene_ordinal?: number;
    summary?: string;
    gap?: string;
  };
};

export type NarrativeLoopConflict = {
  code: string;
  scene_ordinal?: number;
  loop_id?: string;
  message: string;
  start_scene_ordinal?: number;
  end_scene_ordinal?: number;
};

export type NarrativeLoopHook = {
  scene_ordinal: number;
  type?: string;
  summary?: string;
  strength?: number;
  known?: string;
  gap?: string;
  continue_drive?: string;
  next_handoff?: string;
  evidence_paragraph_ids?: string[];
};

export type NarrativeLoopPayoff = {
  scene_ordinal: number;
  type: NarrativePayoffType | string;
  source_type?: string;
  summary?: string;
  strength?: number | null;
  evidence_paragraph_ids?: string[];
};

export type NarrativeLoopView = {
  loop_id: string;
  scope: Record<string, unknown>;
  question: string;
  information_gap: string;
  hook: NarrativeLoopHook[];
  developments: Array<{ scene_ordinal: number; kind?: string }>;
  payoffs: NarrativeLoopPayoff[];
  residual_question: string;
  status: NarrativeLoopStatus | string;
  /** Presentation overlay — does not mutate stored artifact status. */
  display_status?: NarrativeLoopStatus | string;
  evidence: string[];
  confidence: number;
  consistency_status: "consistent" | "inconsistent" | "soft_conflict" | string;
  conflicts: NarrativeLoopConflict[];
  payoff_score_by_scene?: Record<string, number>;
  open_from_scene?: number | null;
  nodes_spanned?: number;
  has_partial_response?: boolean;
  hard_blocked?: boolean;
  soft_conflict?: boolean;
  relation_warning?: string | null;
  primary_relation?: NarrativeRelationAssessment | null;
  candidate_relations?: NarrativeRelationAssessment[];
  relation_assessments?: NarrativeRelationAssessment[];
};

export type NarrativeLoopRisk = {
  risk_type: string;
  loop_id?: string;
  question?: string;
  start_scene_ordinal?: number | null;
  end_scene_ordinal?: number | null;
  span?: number;
  has_partial_response?: boolean;
  summary?: string;
  deterministic?: boolean;
  conflicts?: NarrativeLoopConflict[];
};

export type ScenePayoffClaim = {
  claim: string;
  label: string;
  deterministic: boolean;
  loops: Array<string | undefined>;
  payoff_types: string[];
  evidence_paragraph_ids: string[];
};

export type NarrativeLoopConsistency = {
  status: "consistent" | "inconsistent" | "soft_conflict" | string;
  conflict_count: number;
  hard_conflict_count?: number;
  soft_conflict_count?: number;
  conflicts: NarrativeLoopConflict[];
  user_message?: string | null;
  scope?: Record<string, unknown>;
};

export type ReadingResistanceItem = {
  resistance_type?: string;
  loop_id?: string;
  question?: string;
  start_scene_ordinal?: number | null;
  end_scene_ordinal?: number | null;
  span?: number;
  reason_codes?: string[];
  reasons_zh?: string[];
  summary?: string;
  has_partial_response?: boolean;
  severity?: boolean;
};

type VizWithLoops = ReaderJourneyVisualization & {
  narrative_loops?: NarrativeLoopView[];
  narrative_loop_risks?: NarrativeLoopRisk[];
  reading_resistance?: ReadingResistanceItem[];
  scene_payoff_claims?: Record<string, ScenePayoffClaim>;
  narrative_loop_consistency?: NarrativeLoopConsistency;
  narrative_loop_view_version?: string;
};

export function getNarrativeLoops(visualization: ReaderJourneyVisualization | null | undefined): NarrativeLoopView[] {
  const viz = visualization as VizWithLoops | null | undefined;
  if (!viz) return [];
  if (Array.isArray(viz.narrative_loops)) return viz.narrative_loops;
  return buildNarrativeLoopsFromLegacyVisualization(viz);
}

export function getNarrativeLoopRisks(
  visualization: ReaderJourneyVisualization | null | undefined,
): NarrativeLoopRisk[] {
  const viz = visualization as VizWithLoops | null | undefined;
  if (!viz) return [];
  if (Array.isArray(viz.narrative_loop_risks)) return viz.narrative_loop_risks;
  return deriveOpenLoopRisks(getNarrativeLoops(viz));
}

export function getReadingResistance(
  visualization: ReaderJourneyVisualization | null | undefined,
): ReadingResistanceItem[] {
  const viz = visualization as VizWithLoops | null | undefined;
  if (!viz) return [];
  if (Array.isArray(viz.reading_resistance)) return viz.reading_resistance;
  return [];
}

export function getNarrativeLoopConsistency(
  visualization: ReaderJourneyVisualization | null | undefined,
): NarrativeLoopConsistency | null {
  const viz = visualization as VizWithLoops | null | undefined;
  if (!viz) return null;
  if (viz.narrative_loop_consistency) return viz.narrative_loop_consistency;
  const loops = getNarrativeLoops(viz);
  const conflicts = loops.flatMap((loop) => loop.conflicts || []);
  const hard = conflicts.some(
    (c) =>
      String(c.code || "").startsWith("scope_") ||
      ["fingerprint_mismatch", "run_mismatch", "data_integrity_failed", "cross_book_contamination", "no_text_evidence"].includes(
        String(c.code || ""),
      ),
  );
  const soft = conflicts.length > 0 && !hard;
  return {
    status: hard ? "inconsistent" : soft ? "soft_conflict" : "consistent",
    conflict_count: conflicts.length,
    conflicts,
    user_message: hard ? HARD_BLOCK_USER_MESSAGE : soft ? SOFT_CONFLICT_USER_MESSAGE : null,
  };
}

export function getScenePayoffClaim(
  visualization: ReaderJourneyVisualization | null | undefined,
  sceneOrdinal: number,
): ScenePayoffClaim | null {
  const viz = visualization as VizWithLoops | null | undefined;
  if (!viz) return null;
  const fromApi = viz.scene_payoff_claims?.[String(sceneOrdinal)];
  if (fromApi) return fromApi;
  return scenePayoffClaimFromLoops(getNarrativeLoops(viz), sceneOrdinal, viz);
}

export function loopsForScene(
  loops: NarrativeLoopView[],
  sceneOrdinal: number,
): NarrativeLoopView[] {
  return loops.filter((loop) => {
    if (loop.open_from_scene === sceneOrdinal) return true;
    if ((loop.developments || []).some((d) => d.scene_ordinal === sceneOrdinal)) return true;
    if ((loop.hook || []).some((h) => h.scene_ordinal === sceneOrdinal)) return true;
    if ((loop.payoffs || []).some((p) => p.scene_ordinal === sceneOrdinal)) return true;
    return false;
  });
}

export function formatPayoffClaimLabel(claim: ScenePayoffClaim | null | undefined, payoffScore?: number | null): string {
  if (!claim) {
    if (payoffScore == null || !Number.isFinite(payoffScore)) return "本场回报数据不足。";
    if (payoffScore >= 70) return INCONSISTENT_USER_MESSAGE;
    if (payoffScore >= 40) return "本场完成部分兑现，核心问题仍未完全回收。";
    if (payoffScore > 0) return "本场提供少量线索或部分回答，核心问题仍未兑现。";
    return "本场未提供有效兑现。";
  }
  if (!claim.deterministic) return claim.label || INCONSISTENT_USER_MESSAGE;
  if (claim.claim === "full") return "本场对前文问题完成较强兑现。";
  if (claim.claim === "partial") return "本场完成部分兑现，核心问题仍未完全回收。";
  if (claim.claim === "transformed") return "本场将问题转化为新的开放问题。";
  if (claim.claim === "reversal") return "本场以反转方式回应前文问题。";
  if (claim.claim === "none") return "本场未提供有效兑现。";
  return claim.label || INCONSISTENT_USER_MESSAGE;
}

export function formatHookHandoffFromLoops(
  loops: NarrativeLoopView[],
  sceneOrdinal: number,
): { text: string | null; hint: string | null } {
  const related = loopsForScene(loops, sceneOrdinal);
  const inconsistent = related.some((loop) => loop.consistency_status === "inconsistent");
  if (inconsistent) {
    return { text: null, hint: INCONSISTENT_USER_MESSAGE };
  }
  for (const loop of related) {
    for (const hook of loop.hook || []) {
      if (hook.scene_ordinal !== sceneOrdinal) continue;
      if (hook.next_handoff?.trim()) return { text: hook.next_handoff.trim(), hint: null };
    }
    // Fall back: development / residual on later nodes counts as continuation.
    const later = (loop.developments || []).filter((d) => d.scene_ordinal > sceneOrdinal);
    if (later.length) {
      return {
        text: `后续在场景 ${later.map((d) => d.scene_ordinal).join("、")} 继续推进「${loop.question}」`,
        hint: null,
      };
    }
    if (loop.residual_question && loop.status === "open") {
      return {
        text: null,
        hint: `开放问题「${loop.question}」尚未识别出明确后续承接。`,
      };
    }
  }
  return { text: null, hint: "当前钩子尚未识别出明确的后续承接。" };
}

export function formatOpenLoopRiskSummary(risk: NarrativeLoopRisk): string {
  if (risk.risk_type === "narrative_loop_inconsistent") {
    return HARD_BLOCK_USER_MESSAGE;
  }
  if (risk.summary?.trim()) return risk.summary.trim();
  const question = (risk.question || "未命名问题").trim();
  const start = risk.start_scene_ordinal;
  const span = risk.span ?? 1;
  const partial = risk.has_partial_response ? "存在部分回应，" : "尚无有效回应，";
  const startText = start != null ? `从场景 ${start} 起` : "从当前节点起";
  return `开放问题「${question}」${startText}已跨越 ${span} 个节点，${partial}可能降低阅读动力。`;
}

export function buildNarrativeLoopsFromLegacyVisualization(
  visualization: ReaderJourneyVisualization,
): NarrativeLoopView[] {
  const scope = {
    level: "chapter",
    scene_contract_version: visualization.calibration_status?.scene_contract_version,
    source: "legacy_client_adapter",
  };
  const lifecycle = visualization.question_lifecycle || [];
  if (lifecycle.length) {
    return lifecycle.map((item) => {
      const setup = item.setup_scene;
      const node = visualization.scene_nodes.find((n) => n.scene_ordinal === setup);
      const payoffNode =
        item.payoff_scene != null
          ? visualization.scene_nodes.find((n) => n.scene_ordinal === item.payoff_scene)
          : undefined;
      const payoffs = (payoffNode?.payoffs || []).map((p) => ({
        scene_ordinal: payoffNode!.scene_ordinal,
        type: "full" as const,
        source_type: p.type,
        summary: p.summary,
        strength: p.strength ?? null,
        evidence_paragraph_ids: p.evidence_paragraph_ids || [],
      }));
      const score = payoffNode?.scores?.payoff;
      const conflicts: NarrativeLoopConflict[] = [];
      if (score != null && score >= 70 && payoffs.length === 0) {
        conflicts.push({
          code: "payoff_score_without_entity",
          scene_ordinal: payoffNode!.scene_ordinal,
          message: `Scene ${payoffNode!.scene_ordinal}: payoff_score without entity`,
        });
      }
      const softOnly = conflicts.length > 0;
      return {
        loop_id: item.question_id,
        scope,
        question: item.question_text,
        information_gap: node?.primary_hook?.gap || "",
        hook: (node?.hooks || []).map((h) => ({
          scene_ordinal: setup,
          type: h.type,
          summary: h.summary,
          strength: h.strength,
          known: h.known,
          gap: h.gap,
          continue_drive: h.continue_drive,
          next_handoff: h.next_handoff,
          evidence_paragraph_ids: h.evidence_paragraph_ids || [],
        })),
        developments: (item.development_scenes || []).map((scene_ordinal) => ({
          scene_ordinal,
          kind: "development",
        })),
        payoffs,
        residual_question: item.status === "open" || item.status === "progressing" ? item.question_text : "",
        status: mapLifecycleStatus(item.status),
        evidence: [
          ...(node?.primary_hook?.evidence_paragraph_ids || []),
          ...payoffs.flatMap((p) => p.evidence_paragraph_ids || []),
        ],
        confidence: (item.strength ?? 50) / 100,
        consistency_status: softOnly ? "soft_conflict" : "consistent",
        soft_conflict: softOnly,
        hard_blocked: false,
        conflicts,
        open_from_scene: setup,
        nodes_spanned: 1 + (item.development_scenes?.length || 0) + (item.payoff_scene != null ? 1 : 0),
        has_partial_response: item.status === "partial" || item.status === "progressing",
        payoff_score_by_scene:
          payoffNode != null ? { [String(payoffNode.scene_ordinal)]: payoffNode.scores.payoff } : {},
      };
    });
  }

  const chains = [
    visualization.primary_question_chain,
    ...(visualization.phase_question_chains || []),
    ...(visualization.secondary_question_chains || []),
  ].filter(Boolean);

  return chains.map((chain) => {
    const created = chain!.created_scene;
    const answered = chain!.answered_scene;
    const node = visualization.scene_nodes.find((n) => n.scene_ordinal === created);
    const answeredNode =
      answered != null ? visualization.scene_nodes.find((n) => n.scene_ordinal === answered) : undefined;
    const payoffs = (answeredNode?.payoffs || []).map((p) => ({
      scene_ordinal: answeredNode!.scene_ordinal,
      type: "full" as const,
      source_type: p.type,
      summary: p.summary,
      strength: p.strength ?? null,
      evidence_paragraph_ids: p.evidence_paragraph_ids || [],
    }));
    const conflicts: NarrativeLoopConflict[] = [];
    if (answeredNode && answeredNode.scores.payoff >= 70 && payoffs.length === 0) {
      conflicts.push({
        code: "payoff_score_without_entity",
        scene_ordinal: answeredNode.scene_ordinal,
        message: `Scene ${answeredNode.scene_ordinal}: payoff_score without entity`,
      });
    }
    const softOnly = conflicts.length > 0;
    return {
      loop_id: chain!.canonical_id,
      scope,
      question: chain!.canonical_question,
      information_gap: node?.primary_hook?.gap || "",
      hook: (node?.hooks || []).map((h) => ({
        scene_ordinal: created,
        ...h,
        evidence_paragraph_ids: h.evidence_paragraph_ids || [],
      })),
      developments: (chain!.carried_scene_ordinals || []).map((scene_ordinal) => ({
        scene_ordinal,
        kind: "carried",
      })),
      payoffs,
      residual_question: chain!.open_at_chapter_end ? chain!.canonical_question : "",
      status: mapChainStatus(chain!.status),
      evidence: payoffs.flatMap((p) => p.evidence_paragraph_ids || []),
      confidence: chain!.confidence <= 1 ? chain!.confidence : chain!.confidence / 100,
      consistency_status: softOnly ? "soft_conflict" : "consistent",
      soft_conflict: softOnly,
      hard_blocked: false,
      conflicts,
      open_from_scene: created,
      nodes_spanned:
        1 + (chain!.carried_scene_ordinals?.length || 0) + (answered != null ? 1 : 0),
      has_partial_response: chain!.status === "partially_answered",
      payoff_score_by_scene:
        answeredNode != null ? { [String(answeredNode.scene_ordinal)]: answeredNode.scores.payoff } : {},
    };
  });
}

function mapLifecycleStatus(status: string): NarrativeLoopStatus {
  if (status === "paid_off" || status === "resolved") return "resolved";
  if (status === "partial" || status === "progressing") return "partially_resolved";
  if (status === "abandoned" || status === "overdue") return "abandoned";
  if (status === "transformed") return "transformed";
  return "open";
}

function mapChainStatus(status: string): NarrativeLoopStatus {
  if (status === "answered") return "resolved";
  if (status === "partially_answered") return "partially_resolved";
  if (status === "transformed") return "transformed";
  if (status === "dropped") return "abandoned";
  return "open";
}

function deriveOpenLoopRisks(loops: NarrativeLoopView[]): NarrativeLoopRisk[] {
  return loops
    .filter((loop) => loop.status === "open" || loop.status === "partially_resolved" || loop.status === "inconsistent")
    .map((loop) => {
      if (loop.consistency_status === "inconsistent" || loop.status === "inconsistent") {
        return {
          risk_type: "narrative_loop_inconsistent",
          loop_id: loop.loop_id,
          question: loop.question,
          start_scene_ordinal: loop.open_from_scene,
          end_scene_ordinal: loop.open_from_scene,
          span: loop.nodes_spanned || 1,
          has_partial_response: Boolean(loop.has_partial_response),
          summary: HARD_BLOCK_USER_MESSAGE,
          deterministic: false,
          conflicts: loop.conflicts,
        };
      }
      const span = loop.nodes_spanned || 1;
      const start = loop.open_from_scene ?? null;
      return {
        risk_type: "open_narrative_loop",
        loop_id: loop.loop_id,
        question: loop.question,
        start_scene_ordinal: start,
        end_scene_ordinal: start != null ? start + Math.max(0, span - 1) : null,
        span,
        has_partial_response: Boolean(loop.has_partial_response),
        summary: formatOpenLoopRiskSummary({
          risk_type: "open_narrative_loop",
          question: loop.question,
          start_scene_ordinal: start,
          span,
          has_partial_response: Boolean(loop.has_partial_response),
        }),
        deterministic: true,
      };
    });
}

function scenePayoffClaimFromLoops(
  loops: NarrativeLoopView[],
  sceneOrdinal: number,
  visualization: ReaderJourneyVisualization,
): ScenePayoffClaim {
  const related = loopsForScene(loops, sceneOrdinal);
  const node = visualization.scene_nodes.find((n) => n.scene_ordinal === sceneOrdinal);
  const score = node?.scores?.payoff;
  if (related.some((loop) => loop.hard_blocked || loop.consistency_status === "inconsistent")) {
    return {
      claim: "inconsistent",
      label: HARD_BLOCK_USER_MESSAGE,
      deterministic: false,
      loops: related.map((l) => l.loop_id),
      payoff_types: [],
      evidence_paragraph_ids: [],
    };
  }
  for (const loop of related) {
    const primary = loop.primary_relation;
    const pref = primary?.payoff_ref;
    if (!primary?.grade || primary.grade === "unsupported") continue;
    if (pref?.scene_ordinal != null && pref.scene_ordinal !== sceneOrdinal) continue;
    if (pref?.scene_ordinal == null && !(loop.payoffs || []).some((p) => p.scene_ordinal === sceneOrdinal)) {
      continue;
    }
    return {
      claim: `relation_${primary.grade}`,
      label: primary.grade_label_zh || primary.label_zh || SOFT_CONFLICT_USER_MESSAGE,
      deterministic: primary.grade === "confirmed" && !loop.soft_conflict,
      loops: related.map((l) => l.loop_id),
      payoff_types: pref?.type ? [String(pref.type)] : [],
      evidence_paragraph_ids: pref?.evidence_paragraph_ids || [],
    };
  }
  const payoffs = related.flatMap((loop) =>
    (loop.payoffs || []).filter((p) => p.scene_ordinal === sceneOrdinal),
  );
  if (payoffs.length) {
    const kinds = payoffs.map((p) => String(p.type));
    const claim = kinds.includes("full")
      ? "full"
      : kinds.includes("transformed_question")
        ? "transformed"
        : kinds.includes("reversal")
          ? "reversal"
          : "partial";
    return {
      claim,
      label:
        claim === "full"
          ? "有效兑现"
          : claim === "partial"
            ? "部分兑现"
            : claim === "transformed"
              ? "转化为新问题"
              : "反转兑现",
      deterministic: true,
      loops: related.map((l) => l.loop_id),
      payoff_types: kinds,
      evidence_paragraph_ids: payoffs.flatMap((p) => p.evidence_paragraph_ids || []),
    };
  }
  if (score != null && score >= 40) {
    return {
      claim: "score_only",
      label: SOFT_CONFLICT_USER_MESSAGE,
      deterministic: false,
      loops: related.map((l) => l.loop_id),
      payoff_types: [],
      evidence_paragraph_ids: [],
    };
  }
  return {
    claim: "none",
    label: "未兑现",
    deterministic: true,
    loops: related.map((l) => l.loop_id),
    payoff_types: [],
    evidence_paragraph_ids: [],
  };
}
