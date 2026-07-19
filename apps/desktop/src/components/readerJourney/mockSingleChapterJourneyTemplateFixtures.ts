/**
 * Phase 1D-A test-only fixtures for single-chapter journey template governance.
 * Does not call models; does not create AnalysisRun / ReaderJourneyRun.
 * All fixtures render through the same canonical ReaderJourneyWorkspace entry.
 */
import type {
  JourneyPhaseVisualization,
  JourneyQuestionChain,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";

export type TemplateChapterFixture = {
  bookId: number;
  bookTitle: string;
  chapterId: number;
  chapterTitle: string;
  tags: string[];
  visualization: ReaderJourneyVisualization;
};

function makeNode(
  bookId: number,
  chapterId: number,
  ordinal: number,
  role: "core" | "secondary" | "beat",
  phaseOrdinal: number,
  options: {
    evidenceCount?: number;
    hasHook?: boolean;
    hasPayoff?: boolean;
    hasRisk?: boolean;
  } = {},
): ReaderJourneyVisualization["scene_nodes"][number] {
  const evidenceCount = options.evidenceCount ?? 1;
  const pad = (n: number) => String(n).padStart(4, "0");
  const prefix = `B${String(bookId).padStart(4, "0")}-C${String(chapterId).padStart(4, "0")}`;
  const evidence = Array.from({ length: evidenceCount }, (_, i) => `${prefix}-P${pad(ordinal * 10 + i)}`);
  return {
    scene_id: bookId * 1000 + chapterId * 100 + ordinal,
    scene_ordinal: ordinal,
    paragraph_range: {
      start_paragraph_id: evidence[0],
      end_paragraph_id: evidence[evidence.length - 1],
    },
    paragraph_count: Math.max(evidenceCount, 2),
    phase_ordinal: phaseOrdinal,
    role,
    importance_score: role === "core" ? 70 : role === "secondary" ? 45 : 20,
    importance_formula_version: "1.1",
    deterministic_reasons: ["template-governance-fixture"],
    scene_value_summary: `Scene ${ordinal} 价值摘要`,
    dominant_emotion: "紧张",
    engagement: { engagement_score: 40 + ordinal * 3 },
    scores: {
      curiosity: 50 + ordinal,
      tension: 40 + ordinal,
      payoff: 35 + ordinal,
      hook: 30 + ordinal * 2,
      information_gain: 45,
      emotional_resonance: 50,
      cognitive_load: 40,
      dropoff_risk: 20,
      valence_start: -10,
      valence_end: 10,
      arousal_start: 30,
      arousal_end: 60,
    },
    reader_question_in: ordinal > 1 ? [{ question: `承接问题 ${ordinal}` }] : [],
    reader_question_created: ordinal === 1 ? [{ question: "核心牵引问题？" }] : [],
    reader_question_answered: [],
    reader_question_out: [{ question: `遗留问题 ${ordinal}` }],
    payoffs: options.hasPayoff
      ? [{ type: "reveal", summary: "阶段兑现", strength: 80 }]
      : [],
    hooks: options.hasHook
      ? [
          {
            type: "mystery",
            summary: "章末悬念",
            gap: "未知威胁",
            continue_drive: "强",
            strength: 85,
          },
        ]
      : [],
    techniques: [{ name: "悬念递进", mechanism: "延迟揭晓", reader_effect: "提高好奇" }],
    risk_points: options.hasRisk
      ? [{ type: "pacing", summary: "节奏偏慢", severity: 60 }]
      : [],
    character_effects: [],
    writing_takeaways: [{ summary: "控制信息密度", applicable_when: "中段推进", avoid_when: "高潮兑现时" }],
    evidence_paragraph_ids: evidence,
    evidence_count: evidence.length,
    confidence: 0.8,
    primary_payoff: options.hasPayoff
      ? { type: "reveal", summary: "阶段兑现", strength: 80 }
      : null,
    primary_hook: options.hasHook
      ? {
          type: "mystery",
          summary: "章末悬念",
          gap: "未知威胁",
          continue_drive: "强",
          strength: 85,
        }
      : null,
    primary_risk: options.hasRisk
      ? { type: "pacing", summary: "节奏偏慢", severity: 60 }
      : null,
  };
}

function makeChain(
  id: string,
  question: string,
  createdScene: number,
  status = "carried",
): JourneyQuestionChain {
  return {
    canonical_id: id,
    canonical_question: question,
    aliases: [],
    source_chain_ids: [id],
    created_scene: createdScene,
    carried_scene_ordinals: [createdScene, Math.min(createdScene + 1, createdScene + 1)],
    transformed_scenes: [],
    answered_scene: null,
    status,
    strength: 70,
    open_at_chapter_end: true,
    confidence: 1,
    merge_reason: "singleton",
    question_type: "goal",
    auto_merged: false,
    lifecycle: [
      { scene_ordinal: createdScene, status: "created" },
      { scene_ordinal: createdScene + 1, status: "carried" },
    ],
    importance: 75,
    importance_formula_version: "1.1",
  };
}

function buildPhases(
  sceneCount: number,
  phaseCount: number,
  longTitles: boolean,
): JourneyPhaseVisualization[] {
  const phases: JourneyPhaseVisualization[] = [];
  const baseSpan = Math.max(1, Math.floor(sceneCount / phaseCount));
  let start = 1;
  for (let i = 1; i <= phaseCount; i += 1) {
    const end =
      i === phaseCount ? sceneCount : Math.min(sceneCount, start + baseSpan - 1);
    const short = `阶段${i}`;
    const long =
      `阶段${i}：超长标题用于验证模板不因标题长度改变 DOM 骨架——读者是否仍跟随主问题推进并愿意翻到下一章`;
    phases.push({
      ordinal: i,
      title: longTitles ? long : short,
      start_scene_ordinal: start,
      end_scene_ordinal: end,
      primary_reader_question: `阶段${i}主问题？`,
      dominant_emotion: "紧张",
      reading_payoff: "信息增量",
      continuation_motivation: "追答案",
      summary: `阶段${i}摘要`,
      confidence: 0.8,
      average_engagement: 50 + i * 5,
      core_scene_count: 1,
      beat_count: 1,
      scene_span: end - start + 1,
    });
    start = end + 1;
  }
  return phases;
}

function phaseForOrdinal(phases: JourneyPhaseVisualization[], ordinal: number): number {
  const found = phases.find(
    (p) => ordinal >= p.start_scene_ordinal && ordinal <= p.end_scene_ordinal,
  );
  return found?.ordinal ?? 1;
}

function buildVisualization(spec: {
  bookId: number;
  chapterId: number;
  chapterTitle: string;
  sceneCount: number;
  phaseCount: number;
  hasQuestionChains: boolean;
  hasHookPayoff: boolean;
  firstSceneEvidence: number;
  longPhaseTitles: boolean;
}): ReaderJourneyVisualization {
  const phases = buildPhases(spec.sceneCount, spec.phaseCount, spec.longPhaseTitles);
  const roles: Array<"core" | "secondary" | "beat"> = ["core", "secondary", "beat"];
  const nodes = Array.from({ length: spec.sceneCount }, (_, index) => {
    const ordinal = index + 1;
    const isLast = ordinal === spec.sceneCount;
    const mid = Math.ceil(spec.sceneCount / 2);
    return makeNode(
      spec.bookId,
      spec.chapterId,
      ordinal,
      roles[index % roles.length],
      phaseForOrdinal(phases, ordinal),
      {
        evidenceCount: ordinal === 1 ? spec.firstSceneEvidence : 1,
        hasHook: spec.hasHookPayoff && isLast,
        hasPayoff: spec.hasHookPayoff && ordinal === mid,
        hasRisk: ordinal === Math.max(2, mid - 1),
      },
    );
  });

  const curveMetrics = [
    "engagement",
    "valence",
    "arousal",
    "curiosity",
    "tension",
    "payoff",
    "hook",
    "dropoff_risk",
  ] as const;

  const curve_series = Object.fromEntries(
    curveMetrics.map((metric) => [
      metric,
      nodes.map((node) => {
        if (metric === "valence") {
          return {
            scene_ordinal: node.scene_ordinal,
            start: node.scores.valence_start,
            end: node.scores.valence_end,
          };
        }
        if (metric === "arousal") {
          return {
            scene_ordinal: node.scene_ordinal,
            start: node.scores.arousal_start,
            end: node.scores.arousal_end,
          };
        }
        const value =
          metric === "engagement"
            ? node.engagement.engagement_score
            : (node.scores[metric as keyof typeof node.scores] as number);
        return { scene_ordinal: node.scene_ordinal, value };
      }),
    ]),
  ) as ReaderJourneyVisualization["curve_series"];

  const primaryChain = spec.hasQuestionChains
    ? makeChain(`cqc-b${spec.bookId}-c${spec.chapterId}`, "主角能否安全回家？", 1)
    : null;

  return {
    visualization_version: "1.1",
    chapter_summary: {
      chapter_id: spec.chapterId,
      chapter_title: spec.chapterTitle,
      diagnosis: spec.hasQuestionChains
        ? "本章以主问题牵引，模板骨架与数据解耦。"
        : "本章无问题链，空状态仍使用同一 Inspector Shell。",
      primary_traction: primaryChain?.canonical_question ?? "（无主问题链）",
      primary_cluster_title: primaryChain?.canonical_question ?? "（无簇）",
      core_scene_count: nodes.filter((n) => n.role === "core").length,
      strong_hook_count: spec.hasHookPayoff ? 1 : 0,
      stage_payoff_count: spec.hasHookPayoff ? 1 : 0,
      max_low_payoff_interval: null,
      max_fragmentation_interval: null,
      strongest_payoff: spec.hasHookPayoff
        ? {
            scene_ordinal: Math.ceil(spec.sceneCount / 2),
            scene_id: nodes[Math.ceil(spec.sceneCount / 2) - 1]?.scene_id ?? 0,
            summary: "阶段兑现",
            strength: 80,
          }
        : null,
      strongest_hook: spec.hasHookPayoff
        ? {
            scene_ordinal: spec.sceneCount,
            scene_id: nodes[spec.sceneCount - 1]?.scene_id ?? 0,
            summary: "章末悬念",
            strength: 85,
          }
        : null,
      weak_interval: "（无）",
      counts: {
        scene_count: spec.sceneCount,
        phase_count: spec.phaseCount,
        question_chain_count: primaryChain ? 1 : 0,
        canonical_chain_count: primaryChain ? 1 : 0,
        core: nodes.filter((n) => n.role === "core").length,
        secondary: nodes.filter((n) => n.role === "secondary").length,
        beat: nodes.filter((n) => n.role === "beat").length,
      },
      peaks: {
        engagement_peak: {
          scene_ordinal: spec.sceneCount,
          value: nodes[spec.sceneCount - 1]?.engagement.engagement_score ?? 0,
        },
        engagement_valley: {
          scene_ordinal: 1,
          value: nodes[0]?.engagement.engagement_score ?? 0,
        },
        engagement_average:
          nodes.reduce((sum, n) => sum + n.engagement.engagement_score, 0) / Math.max(nodes.length, 1),
      },
      expanded_diagnosis: {
        pacing_diagnosis: [],
        chapter_strengths: [],
        chapter_risks: [],
        one_sentence_diagnosis: "模板治理 fixture",
      },
    },
    phases,
    curve_series,
    scene_nodes: nodes,
    role_counts: {
      core: nodes.filter((n) => n.role === "core").length,
      secondary: nodes.filter((n) => n.role === "secondary").length,
      beat: nodes.filter((n) => n.role === "beat").length,
    },
    primary_question_chain: primaryChain,
    phase_question_chains: [],
    secondary_question_chains: [],
    question_clusters: primaryChain
      ? [
          {
            cluster_id: `qcl-b${spec.bookId}-c${spec.chapterId}`,
            cluster_type: "goal",
            cluster_title: primaryChain.canonical_question,
            member_chain_ids: [primaryChain.canonical_id],
            primary_chain_id: primaryChain.canonical_id,
            members: [
              {
                chain_id: primaryChain.canonical_id,
                question: primaryChain.canonical_question,
                relationship: "primary",
                importance: 75,
                created_scene: 1,
                status: "carried",
              },
            ],
            relationships: [],
            confidence: 0.8,
            merge_reason: "singleton",
            importance: 75,
            created_scene: 1,
            primary_question: primaryChain.canonical_question,
          },
        ]
      : [],
    visible_question_clusters: primaryChain
      ? [
          {
            cluster_id: `qcl-b${spec.bookId}-c${spec.chapterId}`,
            cluster_type: "goal",
            cluster_title: primaryChain.canonical_question,
            member_chain_ids: [primaryChain.canonical_id],
            primary_chain_id: primaryChain.canonical_id,
            members: [
              {
                chain_id: primaryChain.canonical_id,
                question: primaryChain.canonical_question,
                relationship: "primary",
                importance: 75,
                created_scene: 1,
                status: "carried",
              },
            ],
            relationships: [],
            confidence: 0.8,
            merge_reason: "singleton",
            importance: 75,
            created_scene: 1,
            primary_question: primaryChain.canonical_question,
          },
        ]
      : [],
    payoff_markers: nodes
      .filter((n) => n.primary_payoff)
      .map((n) => ({
        scene_ordinal: n.scene_ordinal,
        scene_id: n.scene_id,
        type: n.primary_payoff?.type,
        summary: n.primary_payoff?.summary,
        strength: n.primary_payoff?.strength,
      })),
    hook_markers: nodes
      .filter((n) => n.primary_hook)
      .map((n) => ({
        scene_ordinal: n.scene_ordinal,
        scene_id: n.scene_id,
        type: n.primary_hook?.type,
        summary: n.primary_hook?.summary,
        strength: n.primary_hook?.strength,
        gap: n.primary_hook?.gap,
        continue_drive: n.primary_hook?.continue_drive,
      })),
    risk_intervals: [],
    formula_versions: {
      visualization_version: "1.1",
      chain_rank_formula_version: "1.0",
      importance_formula_version: "1.1",
      chain_merge_formula_version: "1.0",
      engagement_formula_version: "1.0",
      hook_select_formula_version: "1.1",
      payoff_derive_formula_version: "1.1",
      cluster_formula_version: "1.1",
    },
    calibration_status: {
      scene_contract_version: "1.2",
      scene_prompt_version: "1.0",
      planner_version: "1.0",
      semantic_source: "template-governance-fixture",
      calibrated: true,
      evidence_coverage: 1,
    },
  };
}

/** Four chapters across two books covering governance matrix rows. */
export function buildSingleChapterTemplateFixtures(): TemplateChapterFixture[] {
  return [
    {
      bookId: 101,
      bookTitle: "戏鬼",
      chapterId: 1001,
      chapterTitle: "第1章 戏鬼回家",
      tags: ["has-questions", "has-hook-payoff", "evidence-sparse", "scenes-14", "phases-4"],
      visualization: buildVisualization({
        bookId: 101,
        chapterId: 1001,
        chapterTitle: "第1章 戏鬼回家",
        sceneCount: 14,
        phaseCount: 4,
        hasQuestionChains: true,
        hasHookPayoff: true,
        firstSceneEvidence: 2,
        longPhaseTitles: false,
      }),
    },
    {
      bookId: 101,
      bookTitle: "戏鬼",
      chapterId: 1002,
      chapterTitle:
        "第2章 这是一个故意写得很长的章节标题用来验证模板标题区域不会因为文案长度而分叉成第二套布局",
      tags: ["no-questions", "no-hook-payoff", "evidence-rich", "scenes-6", "phases-2", "long-title"],
      visualization: buildVisualization({
        bookId: 101,
        chapterId: 1002,
        chapterTitle:
          "第2章 这是一个故意写得很长的章节标题用来验证模板标题区域不会因为文案长度而分叉成第二套布局",
        sceneCount: 6,
        phaseCount: 2,
        hasQuestionChains: false,
        hasHookPayoff: false,
        firstSceneEvidence: 7,
        longPhaseTitles: true,
      }),
    },
    {
      bookId: 202,
      bookTitle: "镜中人",
      chapterId: 2001,
      chapterTitle: "序章 裂隙",
      tags: ["has-questions", "no-hook-payoff", "scenes-9", "phases-3"],
      visualization: buildVisualization({
        bookId: 202,
        chapterId: 2001,
        chapterTitle: "序章 裂隙",
        sceneCount: 9,
        phaseCount: 3,
        hasQuestionChains: true,
        hasHookPayoff: false,
        firstSceneEvidence: 1,
        longPhaseTitles: false,
      }),
    },
    {
      bookId: 202,
      bookTitle: "镜中人",
      chapterId: 2002,
      chapterTitle: "第1章 回声",
      tags: ["no-questions", "has-hook-payoff", "evidence-rich", "scenes-5", "phases-5", "long-phase"],
      visualization: buildVisualization({
        bookId: 202,
        chapterId: 2002,
        chapterTitle: "第1章 回声",
        sceneCount: 5,
        phaseCount: 5,
        hasQuestionChains: false,
        hasHookPayoff: true,
        firstSceneEvidence: 8,
        longPhaseTitles: true,
      }),
    },
  ];
}

export const CANONICAL_TEMPLATE_ENTRY =
  "apps/desktop/src/components/readerJourney/ReaderJourneyWorkspace.tsx";

export const TEMPLATE_SKELETON_REGIONS = [
  "journey-analysis-title",
  "journey-diagnosis-summary",
  "journey-summary-cards",
  "journey-phase-strip-wrap",
  "journey-phase-strip",
  "journey-phase-mobile-select",
  "journey-metric-switcher",
  "journey-curve-legend",
  "journey-curve-svg",
  "journey-rhythm-strip",
  "journey-detail-pane",
  "journey-export-root",
] as const;

export type JourneyTemplateSkeleton = {
  regions: string[];
  exportRoot: boolean;
  inspectorShellPresent: boolean;
  emptyStateSupported: boolean;
  metricKeys: string[];
  phaseNavPresent: boolean;
  curvePresent: boolean;
  rhythmPresent: boolean;
};

export function extractJourneyTemplateSkeleton(root: HTMLElement): JourneyTemplateSkeleton {
  const workspace = root.querySelector<HTMLElement>('[data-testid="journey-workspace"]') ?? root;
  const regions = TEMPLATE_SKELETON_REGIONS.filter((id) => workspace.querySelector(`[data-testid="${id}"]`));
  const exportRoot =
    workspace.querySelector('[data-reader-journey-export-root="true"]') != null ||
    workspace.querySelector('[data-testid="journey-export-root"]') != null;
  const empty =
    workspace.querySelector('[data-testid="journey-detail-empty"]') != null ||
    workspace.querySelector('[data-testid="journey-detail-drawer"]') != null;
  const metricKeys = Array.from(
    workspace.querySelectorAll('[data-testid^="journey-metric-"]'),
  )
    .map((el) => el.getAttribute("data-testid") || "")
    .filter((id) => id.startsWith("journey-metric-") && id !== "journey-metric-select" && id !== "journey-metric-select-menu" && id !== "journey-metric-switcher")
    .sort();

  return {
    regions,
    exportRoot,
    inspectorShellPresent: workspace.querySelector('[data-testid="journey-detail-pane"]') != null,
    emptyStateSupported: empty,
    metricKeys,
    phaseNavPresent: workspace.querySelector('[data-testid="journey-phase-strip"]') != null,
    curvePresent: workspace.querySelector('[data-testid="journey-curve-svg"]') != null,
    rhythmPresent: workspace.querySelector('[data-testid="journey-rhythm-strip"]') != null,
  };
}

export function skeletonSignature(skeleton: JourneyTemplateSkeleton): string {
  return JSON.stringify({
    regions: skeleton.regions,
    exportRoot: skeleton.exportRoot,
    inspectorShellPresent: skeleton.inspectorShellPresent,
    emptyStateSupported: skeleton.emptyStateSupported,
    phaseNavPresent: skeleton.phaseNavPresent,
    curvePresent: skeleton.curvePresent,
    rhythmPresent: skeleton.rhythmPresent,
  });
}
