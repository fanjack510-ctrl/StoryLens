import type {
  JourneyQuestionChain,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";

function makeNode(
  ordinal: number,
  role: "core" | "secondary" | "beat",
  engagement: number,
): ReaderJourneyVisualization["scene_nodes"][number] {
  const sceneId = 100 + ordinal;
  return {
    scene_id: sceneId,
    scene_ordinal: ordinal,
    paragraph_range: {
      start_paragraph_id: `B0001-C0002-P${String(ordinal * 10).padStart(4, "0")}`,
      end_paragraph_id: `B0001-C0002-P${String(ordinal * 10 + 2).padStart(4, "0")}`,
    },
    paragraph_count: role === "beat" ? 2 : 4,
    phase_ordinal: ordinal <= 3 ? 1 : ordinal <= 7 ? 2 : ordinal <= 11 ? 3 : 4,
    role,
    importance_score: role === "core" ? 70 : role === "secondary" ? 45 : 20,
    importance_formula_version: "1.1",
    deterministic_reasons: ["test"],
    scene_value_summary: `场景 ${ordinal} 进一步推进人物关系与阅读期待。`,
    dominant_emotion: "紧张",
    engagement: { engagement_score: engagement },
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
    reader_question_created: ordinal === 1 ? [{ question: "主角能否回家？" }] : [],
    reader_question_answered: [],
    reader_question_out: [{ question: `遗留问题 ${ordinal}` }],
    payoffs: ordinal === 5 ? [{ type: "reveal", summary: "身份揭露", strength: 80 }] : [],
    hooks:
      ordinal === 14
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
    risk_points: ordinal === 8 ? [{ type: "pacing", summary: "节奏偏慢", severity: 60 }] : [],
    character_effects: [],
    writing_takeaways:
      ordinal === 1
        ? [
            {
              summary: "用具体动作建立身份疑点",
              applicable_when: "开篇需要快速埋下身份悬念时",
              avoid_when: "信息已过度堆叠时",
            },
          ]
        : [{ summary: "控制信息密度", applicable_when: "中段推进", avoid_when: "高潮兑现时" }],
    evidence_paragraph_ids: [`B0001-C0002-P${String(ordinal * 10).padStart(4, "0")}`],
    evidence_count: 1,
    confidence: 0.8,
    primary_payoff:
      ordinal === 5 ? { type: "reveal", summary: "身份揭露", strength: 80 } : null,
    primary_hook:
      ordinal === 14
        ? {
            type: "mystery",
            summary: "章末悬念",
            gap: "未知威胁",
            continue_drive: "强",
            strength: 85,
          }
        : null,
    primary_risk: ordinal === 8 ? { type: "pacing", summary: "节奏偏慢", severity: 60 } : null,
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
    carried_scene_ordinals: [createdScene, createdScene + 1],
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

export function buildMockReaderJourneyVisualization(): ReaderJourneyVisualization {
  const roles: Array<"core" | "secondary" | "beat"> = [
    "core",
    "secondary",
    "beat",
    "secondary",
    "core",
    "beat",
    "secondary",
    "core",
    "beat",
    "secondary",
    "core",
    "beat",
    "secondary",
    "core",
  ];
  const nodes = roles.map((role, index) => makeNode(index + 1, role, 35 + index * 4));

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

  const primaryChain = makeChain("cqc-primary", "主角能否安全回家？", 1);
  const phaseChain2 = makeChain("cqc-phase-2", "障碍来自何方？", 4);
  const phaseChain3 = makeChain("cqc-phase-3", "谁才是真正的敌人？", 8);

  return {
    visualization_version: "1.1",
    chapter_summary: {
      chapter_id: 2,
      chapter_title: "第1章 戏鬼回家",
      diagnosis: "本章以回家悬念牵引，中段信息密度偏高，章末钩子较强。",
      primary_traction: "主角能否安全回家？",
      primary_cluster_title: "主角能否安全回家？",
      core_scene_count: 5,
      strong_hook_count: 1,
      stage_payoff_count: 1,
      max_low_payoff_interval: {
        risk_type: "consecutive_no_payoff",
        start_scene_ordinal: 6,
        end_scene_ordinal: 7,
        span: 2,
      },
      max_fragmentation_interval: {
        risk_type: "over_fragmented_beats",
        start_scene_ordinal: 2,
        end_scene_ordinal: 6,
        span: 5,
      },
      strongest_payoff: {
        scene_ordinal: 5,
        scene_id: 105,
        summary: "身份揭露",
        strength: 80,
      },
      strongest_hook: {
        scene_ordinal: 14,
        scene_id: 114,
        summary: "章末悬念",
        strength: 85,
      },
      weak_interval: "Scene 7—8 (low_engagement)",
      counts: {
        scene_count: 14,
        phase_count: 4,
        question_chain_count: 6,
        canonical_chain_count: 4,
        core: 5,
        secondary: 5,
        beat: 4,
      },
      peaks: {
        engagement_peak: { scene_ordinal: 14, value: 87 },
        engagement_valley: { scene_ordinal: 3, value: 47 },
        engagement_average: 63.5,
      },
      expanded_diagnosis: {
        pacing_diagnosis: [{ label: "中段偏密" }],
        chapter_strengths: ["开篇钩子明确"],
        chapter_risks: ["中段连续 beat 偏多"],
        one_sentence_diagnosis: "本章以回家悬念牵引，中段信息密度偏高，章末钩子较强。",
      },
    },
    phases: [
      {
        ordinal: 1,
        title: "入局",
        start_scene_ordinal: 1,
        end_scene_ordinal: 3,
        primary_reader_question: "主角为何回家？",
        dominant_emotion: "不安",
        reading_payoff: "建立威胁",
        continuation_motivation: "想知道后果",
        summary: "建立主问题",
        confidence: 0.8,
        average_engagement: 52,
        core_scene_count: 1,
        beat_count: 1,
        scene_span: 3,
      },
      {
        ordinal: 2,
        title: "推进",
        start_scene_ordinal: 4,
        end_scene_ordinal: 7,
        primary_reader_question: "障碍是什么？",
        dominant_emotion: "紧张",
        reading_payoff: "信息增量",
        continuation_motivation: "追答案",
        summary: "冲突升级",
        confidence: 0.8,
        average_engagement: 58,
        core_scene_count: 1,
        beat_count: 1,
        scene_span: 4,
      },
      {
        ordinal: 3,
        title: "转折",
        start_scene_ordinal: 8,
        end_scene_ordinal: 11,
        primary_reader_question: "真相何时揭露？",
        dominant_emotion: "震惊",
        reading_payoff: "关键反转",
        continuation_motivation: "看结局",
        summary: "反转与代价",
        confidence: 0.8,
        average_engagement: 66,
        core_scene_count: 2,
        beat_count: 1,
        scene_span: 4,
      },
      {
        ordinal: 4,
        title: "收束",
        start_scene_ordinal: 12,
        end_scene_ordinal: 14,
        primary_reader_question: "能否脱身？",
        dominant_emotion: "余悸",
        reading_payoff: "章末钩子",
        continuation_motivation: "强",
        summary: "开放悬念",
        confidence: 0.8,
        average_engagement: 78,
        core_scene_count: 2,
        beat_count: 1,
        scene_span: 3,
      },
    ],
    curve_series,
    scene_nodes: nodes,
    role_counts: { core: 5, secondary: 5, beat: 4 },
    primary_question_chain: primaryChain,
    phase_question_chains: [phaseChain2, phaseChain3],
    secondary_question_chains: [makeChain("cqc-secondary-1", "配角动机是什么？", 6, "open")],
    question_clusters: [
      {
        cluster_id: "qcl-primary",
        cluster_type: "goal",
        cluster_title: "主角能否安全回家？",
        member_chain_ids: ["cqc-primary", "cqc-phase-2"],
        primary_chain_id: "cqc-primary",
        members: [
          {
            chain_id: "cqc-primary",
            question: "主角能否安全回家？",
            relationship: "primary",
            importance: 75,
            created_scene: 1,
            status: "carried",
          },
          {
            chain_id: "cqc-phase-2",
            question: "障碍来自何方？",
            relationship: "escalation",
            importance: 70,
            created_scene: 4,
            status: "carried",
          },
        ],
        relationships: [
          {
            from_chain_id: "cqc-phase-2",
            to_chain_id: "cqc-primary",
            relationship: "escalation",
          },
        ],
        confidence: 0.72,
        merge_reason: "escalation",
        importance: 75,
        created_scene: 1,
        primary_question: "主角能否安全回家？",
      },
    ],
    visible_question_clusters: [
      {
        cluster_id: "qcl-primary",
        cluster_type: "goal",
        cluster_title: "主角能否安全回家？",
        member_chain_ids: ["cqc-primary", "cqc-phase-2"],
        primary_chain_id: "cqc-primary",
        members: [
          {
            chain_id: "cqc-primary",
            question: "主角能否安全回家？",
            relationship: "primary",
            importance: 75,
            created_scene: 1,
            status: "carried",
          },
          {
            chain_id: "cqc-phase-2",
            question: "障碍来自何方？",
            relationship: "escalation",
            importance: 70,
            created_scene: 4,
            status: "carried",
          },
        ],
        relationships: [],
        confidence: 0.72,
        merge_reason: "escalation",
        importance: 75,
        created_scene: 1,
        primary_question: "主角能否安全回家？",
      },
    ],
    all_hook_count: 3,
    visible_hook_count: 1,
    suppressed_hook_count: 2,
    suppressed_hooks: [
      {
        scene_ordinal: 3,
        scene_id: 103,
        type: "mystery",
        summary: "被抑制的弱钩子",
        strength: 45,
        visible: false,
        suppression_reason: "below_visible_strength_threshold",
      },
    ],
    semantic_payoff_count: 1,
    derived_payoff_count: 0,
    deduped_payoff_count: 1,
    visible_payoff_count: 1,
    semantic_payoffs: [],
    derived_micro_payoffs: [],
    scene_level_distribution: {
      role_counts: { core: 5, secondary: 5, beat: 4 },
      classifications: nodes.map((node) => ({
        scene_ordinal: node.scene_ordinal,
        importance_score: node.importance_score,
        percentile: 50,
        forced_floor_reason: node.scene_ordinal === 14 ? "chapter_end" : null,
        final_level: node.role,
        classification_reasons: node.deterministic_reasons,
        importance_formula_version: "1.1",
      })),
    },
    visual_density_warnings: [],
    payoff_markers: [
      {
        scene_ordinal: 5,
        scene_id: 105,
        type: "reveal",
        summary: "身份揭露",
        strength: 80,
      },
    ],
    hook_markers: [
      {
        scene_ordinal: 14,
        scene_id: 114,
        type: "mystery",
        summary: "章末悬念",
        strength: 85,
        gap: "未知威胁",
        continue_drive: "强",
      },
    ],
    risk_intervals: [
      {
        risk_type: "low_engagement",
        start_scene_ordinal: 7,
        end_scene_ordinal: 8,
        span: 2,
        summary: "Scene 7—8 engagement持续偏低",
        trigger: "engagement<40，连续>=2",
        needs_review: false,
      },
    ],
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
      semantic_source: "model+deterministic_calibration",
      calibrated: true,
      evidence_coverage: 1,
    },
  };
}
