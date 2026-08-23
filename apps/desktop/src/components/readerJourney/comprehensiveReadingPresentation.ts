/**
 * CHG-20260729-003 — presentation-layer comprehensive reading factors.
 * Does NOT modify formula_v2 / reading_momentum computation.
 * Deterministic derive only (explanation_source: derived | unavailable).
 */

import type {
  JourneyPhaseVisualization,
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import {
  compositeRoleFitLabel,
  type CompositeRoleFitLabel,
} from "./observationLenses";
import { resolveSceneStageAssignment } from "./journeyStageBands";

export type ExplanationSource = "derived" | "unavailable";

export type ComprehensiveReadingFactors = {
  primary_driver: string | null;
  primary_drag: string | null;
  explanation_source: ExplanationSource;
};

export type ComprehensiveKeyNodeKind = "reading_rise" | "reading_drop" | "composite_turn";

export type ComprehensiveKeyNode = {
  scene_ordinal: number;
  kind: ComprehensiveKeyNodeKind;
  label: string;
  detail: string | null;
};

const MOMENTUM_DELTA_MARK = 7;
const MAX_KEY_NODES = 5;
const SHORT_LABEL_MAX = 12;
const STAGE_SUMMARY_MAX = 32;
const INSIGHT_MAX = 160;
const INSIGHT_MIN = 60;

type ScoreBag = {
  momentum: number | null;
  plot: number | null;
  tension: number | null;
  emotion: number | null;
  hook: number | null;
  payoff: number | null;
  pacing: number | null;
  pacingFit: number | null;
  clarity: number | null;
};

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function resolveOverallReadingScore(node: JourneySceneNode): number | null {
  if (node.overall_reading_score != null && Number.isFinite(node.overall_reading_score)) {
    return Number(node.overall_reading_score);
  }
  const m = node.scores?.reading_momentum;
  if (typeof m === "number" && Number.isFinite(m)) return m;
  const eng = node.engagement?.engagement_score;
  if (typeof eng === "number" && Number.isFinite(eng)) return eng;
  return null;
}

/** Single source of truth for fit — prefer persisted composite_role_fit. */
export function resolveCompositeRoleFit(node: JourneySceneNode): CompositeRoleFitLabel {
  const existing = node.composite_role_fit;
  if (existing === "合适" || existing === "偏弱" || existing === "偏强" || existing === "无法判断") {
    return existing;
  }
  return compositeRoleFitLabel(
    resolveOverallReadingScore(node),
    node.scene_role ?? null,
  );
}

function scoreBag(node: JourneySceneNode): ScoreBag {
  const s = node.scores ?? ({} as JourneySceneNode["scores"]);
  const emotion =
    num(s.emotional_investment) ??
    (num(s.arousal_start) != null && num(s.arousal_end) != null
      ? ((s.arousal_start as number) + (s.arousal_end as number)) / 2
      : num(s.arousal_start) ?? num(s.arousal_end));
  return {
    momentum: resolveOverallReadingScore(node),
    plot: num(s.plot_progress),
    tension: num(s.reading_tension),
    emotion,
    hook: num(s.hook),
    payoff: num(s.payoff),
    pacing: num(s.pacing_speed),
    pacingFit: num(s.pacing_fit),
    clarity: num(s.clarity),
  };
}

type Candidate = { text: string; priority: number; strength: number };

function roleFamily(sceneRole: string | null | undefined): string {
  return String(sceneRole || "").trim().toLowerCase();
}

function isAftermathLike(role: string): boolean {
  return role === "aftermath" || role === "closed_end" || role === "transition";
}

function isClimaxLike(role: string): boolean {
  return role === "climax" || role === "escalation" || role === "reveal";
}

function isSetupLike(role: string): boolean {
  return role === "setup" || role === "open_end";
}

/**
 * Deterministic primary_driver / primary_drag from existing scores + fit + role.
 * Never uses fixed global thresholds alone for fit; fit must come from resolveCompositeRoleFit.
 */
export function deriveComprehensiveReadingFactors(
  node: JourneySceneNode,
  ctx: {
    prev?: JourneySceneNode | null;
    next?: JourneySceneNode | null;
  } = {},
): ComprehensiveReadingFactors {
  const bag = scoreBag(node);
  const fit = resolveCompositeRoleFit(node);
  const role = roleFamily(node.scene_role);
  const drivers: Candidate[] = [];
  const drags: Candidate[] = [];

  const pushDriver = (text: string, priority: number, strength: number) => {
    if (strength < 55) return;
    drivers.push({ text, priority, strength });
  };
  const pushDrag = (text: string, priority: number, strength: number) => {
    if (strength < 40 && fit === "合适") return;
    drags.push({ text, priority, strength });
  };

  // --- Drivers ---
  if (bag.payoff != null && bag.payoff >= 65 && (bag.hook == null || bag.payoff >= (bag.hook ?? 0))) {
    pushDriver("前置钩子得到回应", 10, bag.payoff);
  } else if (bag.hook != null && bag.hook >= 65 && (bag.payoff == null || bag.payoff < 45)) {
    pushDriver("新钩子有效建立", 20, bag.hook);
  }

  if (bag.plot != null && bag.plot >= 65 && !isAftermathLike(role)) {
    pushDriver(
      bag.plot >= 78 ? "剧情产生实质推进" : "信息揭示改变局势",
      isClimaxLike(role) ? 15 : 30,
      bag.plot,
    );
  }

  if (bag.tension != null && bag.tension >= 65 && (isClimaxLike(role) || role === "investigation")) {
    pushDriver(bag.tension >= 78 ? "冲突明显升级" : "风险与不确定性增加", 25, bag.tension);
  }

  if (bag.emotion != null && bag.emotion >= 68 && !isSetupLike(role)) {
    pushDriver("情绪变化清晰有效", 40, bag.emotion);
  }

  if (
    fit === "合适" &&
    ((bag.pacingFit != null && bag.pacingFit >= 70) ||
      (bag.pacing != null && bag.pacing >= 40 && bag.pacing <= 70))
  ) {
    pushDriver("节奏与场景任务匹配", 50, bag.pacingFit ?? 72);
  }

  if (isAftermathLike(role) && bag.payoff != null && bag.payoff >= 55) {
    pushDriver("场景完成有效收束", 18, bag.payoff);
  }

  if (isSetupLike(role) && bag.plot != null && bag.plot >= 45 && bag.plot < 65) {
    pushDriver("前后承接清楚", 55, 60 + (bag.plot - 45));
  }

  const prevMom = ctx.prev ? resolveOverallReadingScore(ctx.prev) : null;
  if (
    bag.momentum != null &&
    prevMom != null &&
    bag.momentum - prevMom >= MOMENTUM_DELTA_MARK &&
    bag.plot != null &&
    bag.plot >= 60
  ) {
    pushDriver("人物目标更加明确", 35, bag.momentum);
  }

  // --- Drags ---
  if (fit === "偏强") {
    if (bag.pacing != null && bag.pacing >= 70) {
      pushDrag("节奏偏快", 10, bag.pacing);
    } else {
      pushDrag("与当前场景任务不匹配", 12, 70);
    }
  }

  if (fit === "偏弱") {
    pushDrag("与当前场景任务不匹配", 11, 68);
  }

  if (bag.plot != null && bag.plot <= 45) {
    pushDrag("剧情推进有限", isAftermathLike(role) ? 45 : 20, 100 - bag.plot);
  }

  if (bag.tension != null && bag.tension <= 42 && isClimaxLike(role)) {
    pushDrag("阅读张力不足", 22, 100 - bag.tension);
  } else if (bag.tension != null && bag.tension <= 38) {
    pushDrag("阅读张力不足", 40, 100 - bag.tension);
  }

  if (bag.hook != null && bag.hook >= 55 && (bag.payoff == null || bag.payoff <= 40)) {
    pushDrag("钩子缺少回应", 18, bag.hook);
  }

  if (bag.emotion != null && bag.emotion <= 42 && !isSetupLike(role) && bag.plot != null && bag.plot >= 60) {
    pushDrag("情绪铺垫不足", 28, 100 - bag.emotion);
  }

  if (bag.pacing != null && bag.pacing <= 35 && !isAftermathLike(role) && !isSetupLike(role)) {
    pushDrag("节奏拖慢", 35, 100 - bag.pacing);
  }

  if (
    bag.momentum != null &&
    prevMom != null &&
    prevMom - bag.momentum >= MOMENTUM_DELTA_MARK &&
    bag.plot != null &&
    bag.plot <= 50
  ) {
    pushDrag("前后承接较弱", 30, prevMom - bag.momentum);
  }

  if (isAftermathLike(role) && bag.payoff != null && bag.payoff < 45) {
    pushDrag("收束缺少有效回应", 16, 100 - bag.payoff);
  }

  if (isSetupLike(role) && bag.hook != null && bag.hook < 45) {
    pushDrag("钩子缺少回应", 25, 100 - bag.hook);
  }

  const pick = (list: Candidate[]): string | null => {
    if (!list.length) return null;
    list.sort((a, b) => a.priority - b.priority || b.strength - a.strength || a.text.localeCompare(b.text, "zh"));
    return list[0].text;
  };

  const driver = pick(drivers);
  let drag = pick(drags);
  if (driver && drag && driver === drag) {
    drag = pick(drags.filter((d) => d.text !== driver)) ?? null;
  }

  if (!driver && !drag) {
    return { primary_driver: null, primary_drag: null, explanation_source: "unavailable" };
  }
  return {
    primary_driver: driver,
    primary_drag: drag,
    explanation_source: "derived",
  };
}

function truncateZh(text: string, max: number): string {
  const chars = Array.from(text);
  if (chars.length <= max) return text;
  return chars.slice(0, max).join("");
}

/** Bottom scene short reason — max 12 Chinese chars. */
export function buildComprehensiveShortLabel(
  factors: ComprehensiveReadingFactors,
  opts: { preferSingle?: boolean } = {},
): string | null {
  const d = factors.primary_driver;
  const g = factors.primary_drag;
  if (!d && !g) return null;
  if (opts.preferSingle || !d || !g) {
    return truncateZh(d || g || "", SHORT_LABEL_MAX);
  }
  // Prefer compact "A，B" within 12 chars
  const combo = `${truncateZh(d, 5)}，${truncateZh(g, 5)}`;
  if (Array.from(combo).length <= SHORT_LABEL_MAX) return combo;
  // Prefer drag when fit mismatch language, else higher-impact: keep driver if shorter needed
  const single = Array.from(d).length <= Array.from(g).length ? d : g;
  return truncateZh(single, SHORT_LABEL_MAX);
}

function dimDelta(curr: JourneySceneNode, prev: JourneySceneNode): {
  up: number;
  down: number;
} {
  const a = scoreBag(curr);
  const b = scoreBag(prev);
  const keys: (keyof ScoreBag)[] = ["plot", "tension", "emotion", "hook", "payoff", "pacing"];
  let up = 0;
  let down = 0;
  for (const k of keys) {
    const c = a[k];
    const p = b[k];
    if (c == null || p == null) continue;
    if (c - p >= 10) up += 1;
    if (p - c >= 10) down += 1;
  }
  return { up, down };
}

export function deriveComprehensiveKeyNodes(
  visualization: ReaderJourneyVisualization,
): ComprehensiveKeyNode[] {
  const nodes = [...(visualization.scene_nodes || [])]
    .filter((n) => n.include_in_main_curve !== false && n.role !== "beat" && n.node_type !== "beat")
    .sort((a, b) => a.scene_ordinal - b.scene_ordinal);

  type Cand = ComprehensiveKeyNode & { priority: number; magnitude: number };
  const cands: Cand[] = [];

  for (let i = 1; i < nodes.length; i += 1) {
    const prev = nodes[i - 1];
    const curr = nodes[i];
    const prevM = resolveOverallReadingScore(prev);
    const currM = resolveOverallReadingScore(curr);
    if (prevM == null || currM == null) continue;
    const delta = currM - prevM;
    const fitPrev = resolveCompositeRoleFit(prev);
    const fitCurr = resolveCompositeRoleFit(curr);
    const dims = dimDelta(curr, prev);
    const factors = deriveComprehensiveReadingFactors(curr, { prev, next: nodes[i + 1] });
    const stage = resolveSceneStageAssignment(visualization, curr.scene_ordinal, curr);
    const prevStage = resolveSceneStageAssignment(visualization, prev.scene_ordinal, prev);
    const nearStageBoundary = stage.stageKey !== prevStage.stageKey;

    const turn =
      (dims.up >= 2 && dims.down >= 1) ||
      (dims.down >= 2 && dims.up >= 1) ||
      (Math.abs(delta) >= MOMENTUM_DELTA_MARK && nearStageBoundary && dims.up + dims.down >= 2) ||
      (factors.primary_driver === "前置钩子得到回应" && factors.primary_drag == null && dims.up >= 2);

    if (turn) {
      const detail = factors.primary_driver || factors.primary_drag || "多维同步变化";
      cands.push({
        scene_ordinal: curr.scene_ordinal,
        kind: "composite_turn",
        label: "综合转折",
        detail,
        priority: 1,
        magnitude: Math.abs(delta) + dims.up * 5 + dims.down * 5,
      });
      continue;
    }

    if (delta >= MOMENTUM_DELTA_MARK || (fitPrev === "偏弱" && fitCurr === "合适" && delta >= 6)) {
      cands.push({
        scene_ordinal: curr.scene_ordinal,
        kind: "reading_rise",
        label: "阅读提升",
        detail: factors.primary_driver || "阅读动力上升",
        priority: 2,
        magnitude: delta,
      });
      continue;
    }

    if (delta <= -MOMENTUM_DELTA_MARK || (fitPrev === "合适" && fitCurr === "偏弱" && delta <= -6)) {
      cands.push({
        scene_ordinal: curr.scene_ordinal,
        kind: "reading_drop",
        label: "阅读下降",
        detail: factors.primary_drag || "阅读动力下降",
        priority: 3,
        magnitude: Math.abs(delta),
      });
    }
  }

  // One node per scene — keep best priority
  const byScene = new Map<number, Cand>();
  for (const c of cands) {
    const prev = byScene.get(c.scene_ordinal);
    if (!prev || c.priority < prev.priority || (c.priority === prev.priority && c.magnitude > prev.magnitude)) {
      byScene.set(c.scene_ordinal, c);
    }
  }

  return [...byScene.values()]
    .sort((a, b) => a.priority - b.priority || b.magnitude - a.magnitude || a.scene_ordinal - b.scene_ordinal)
    .slice(0, MAX_KEY_NODES)
    .map(({ scene_ordinal, kind, label, detail }) => ({ scene_ordinal, kind, label, detail }));
}

export function deriveStageJudgmentSummary(
  visualization: ReaderJourneyVisualization,
  phase: JourneyPhaseVisualization,
): string {
  const nodes = (visualization.scene_nodes || [])
    .filter(
      (n) =>
        n.scene_ordinal >= phase.start_scene_ordinal &&
        n.scene_ordinal <= phase.end_scene_ordinal &&
        n.include_in_main_curve !== false,
    )
    .sort((a, b) => a.scene_ordinal - b.scene_ordinal);

  if (!nodes.length) return "当前阶段表现较为平稳。";

  const scores = nodes.map((n) => resolveOverallReadingScore(n)).filter((v): v is number => v != null);
  if (!scores.length) return "当前阶段表现较为平稳。";

  const first = scores[0];
  const last = scores[scores.length - 1];
  const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
  const max = Math.max(...scores);
  const min = Math.min(...scores);
  const trend = last - first;
  const swing = max - min;

  const factorCounts = new Map<string, number>();
  for (let i = 0; i < nodes.length; i += 1) {
    const f = deriveComprehensiveReadingFactors(nodes[i], {
      prev: i > 0 ? nodes[i - 1] : null,
      next: i + 1 < nodes.length ? nodes[i + 1] : null,
    });
    for (const t of [f.primary_driver, f.primary_drag]) {
      if (!t) continue;
      factorCounts.set(t, (factorCounts.get(t) || 0) + 1);
    }
  }
  const topFactor = [...factorCounts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "zh"))[0]?.[0];

  const stageKey = resolveSceneStageAssignment(
    visualization,
    phase.start_scene_ordinal,
    nodes[0],
  ).stageKey;

  let text: string;
  if (stageKey === "opening") {
    if (trend < -6 || avg < 55) text = "进入较慢，主要依靠信息铺垫";
    else if (trend > 8) text = "前段稳定，阅读期待逐步建立";
    else text = "进入较慢，主要依靠氛围建立";
  } else if (stageKey === "development") {
    if (trend >= 10 || max - first >= 12) text = "中段抬升明显，冲突形成主要推动";
    else if (swing >= 18) text = "阶段波动较大，前后衔接不稳定";
    else if (avg >= 65) text = "推进和张力持续抬升";
    else text = "推进稳定，但张力变化有限";
  } else if (stageKey === "closing") {
    if (trend <= -8 && topFactor?.includes("回应")) text = "完成回应，但结尾阅读动力回落";
    else if (trend <= -8) text = "完成回应，但结尾推动力回落";
    else if (avg >= 60) text = "收束平稳，主要问题已得到回应";
    else text = "收束平稳，主要问题已得到回应";
  } else if (swing < 8 && Math.abs(trend) < 6) {
    text = "当前阶段表现较为平稳。";
  } else if (trend >= 10) {
    text = "中段抬升明显，冲突形成主要推动";
  } else if (trend <= -10) {
    text = "完成回应，但结尾阅读动力回落";
  } else {
    text = "当前阶段表现较为平稳。";
  }

  // Avoid identical mechanical templates across phases by lightly varying with topFactor
  if (topFactor === "节奏偏快" && stageKey === "development") {
    text = "推进稳定，但张力变化有限";
  }
  if (topFactor === "新钩子有效建立" && stageKey === "opening") {
    text = "前段稳定，阅读期待逐步建立";
  }

  return truncateZh(text.replace(/。$/, "") + (text.endsWith("。") ? "。" : ""), STAGE_SUMMARY_MAX);
}

export function buildComprehensiveInsightProse(
  node: JourneySceneNode,
  factors: ComprehensiveReadingFactors,
  existingOverall: string | null | undefined,
): string {
  const existing = (existingOverall || "").trim();
  const hasDriver = Boolean(factors.primary_driver);
  const hasDrag = Boolean(factors.primary_drag);

  if (existing && hasDriver && existing.includes(factors.primary_driver!) && (!hasDrag || existing.includes(factors.primary_drag!))) {
    return truncateZh(existing, INSIGHT_MAX);
  }

  const fit = resolveCompositeRoleFit(node);
  const score = resolveOverallReadingScore(node);
  const scoreHint =
    score == null ? "综合阅读贡献暂难量化" : score >= 70 ? "综合阅读贡献偏强" : score <= 45 ? "综合阅读贡献有限" : "综合阅读贡献中等";

  let prose: string;
  if (hasDriver && hasDrag) {
    prose = `本场景${scoreHint}，主要依靠${factors.primary_driver}拉动继续阅读；同时${factors.primary_drag}，使整体体验略有折扣。`;
  } else if (hasDriver) {
    prose = `本场景${scoreHint}，核心推动来自${factors.primary_driver}，与当前场景任务${fit === "合适" ? "基本匹配" : fit}。`;
  } else if (hasDrag) {
    prose = `本场景${scoreHint}，主要拖累是${factors.primary_drag}，需要结合前后位置理解其作用。`;
  } else if (existing) {
    prose = existing;
  } else {
    prose = `本场景${scoreHint}，适配状态为${fit}；暂无更明确的单点推动或拖累依据。`;
  }

  // Prefer splicing existing insight when it adds unique context
  if (existing && existing.length >= 20 && !prose.includes(existing.slice(0, 12))) {
    const merged = `${prose.replace(/。$/, "")}；${existing}`;
    prose = merged;
  }

  let out = truncateZh(prose, INSIGHT_MAX);
  if (Array.from(out).length < INSIGHT_MIN && existing) {
    out = truncateZh(`${out}${existing}`, INSIGHT_MAX);
  }
  return out;
}

export function enrichVisualizationComprehensivePresentation(
  visualization: ReaderJourneyVisualization,
): ReaderJourneyVisualization {
  const nodes = [...(visualization.scene_nodes || [])].sort(
    (a, b) => a.scene_ordinal - b.scene_ordinal,
  );
  const enrichedNodes = nodes.map((node, index) => {
    const factors = deriveComprehensiveReadingFactors(node, {
      prev: index > 0 ? nodes[index - 1] : null,
      next: index + 1 < nodes.length ? nodes[index + 1] : null,
    });
    const fit = resolveCompositeRoleFit(node);
    const score = resolveOverallReadingScore(node);
    const shortLabel = buildComprehensiveShortLabel(factors);
    const insights = { ...(node.dimension_insights || {}) };
    const overall = buildComprehensiveInsightProse(
      node,
      factors,
      typeof insights.overall_reading === "string" ? insights.overall_reading : null,
    );
    insights.overall_reading = overall;
    return {
      ...node,
      overall_reading_score: score,
      composite_role_fit: fit,
      primary_driver: factors.primary_driver,
      primary_drag: factors.primary_drag,
      explanation_source: factors.explanation_source,
      comprehensive_short_label: shortLabel,
      dimension_insights: insights,
    };
  });

  const withNodes = { ...visualization, scene_nodes: enrichedNodes };
  const keyNodes = deriveComprehensiveKeyNodes(withNodes);
  const phases = (visualization.phases || []).map((phase) => ({
    ...phase,
    stage_judgment_summary: deriveStageJudgmentSummary(withNodes, phase),
  }));

  return {
    ...withNodes,
    phases,
    comprehensive_key_nodes: keyNodes,
  };
}

export const COMPREHENSIVE_READING_COPY = {
  definition:
    "综合判断每个场景对故事理解、阅读期待、情绪体验和阅读流畅度的整体贡献；分数高低需要结合场景任务和前后位置判断。",
  yAxisTitle: "综合阅读表现",
  riskLegend: "阅读阻力",
} as const;
