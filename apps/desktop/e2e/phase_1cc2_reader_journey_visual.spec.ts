import { expect, test } from "@playwright/test";

/** Phase 1C-C.2 Reader Journey visual workspace — mocked API, no real cloud. */

function buildVisualizationFixture() {
  const roles = [
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
  ] as const;

  const sceneNodes = roles.map((role, index) => {
    const ordinal = index + 1;
    return {
      scene_id: 100 + ordinal,
      scene_ordinal: ordinal,
      paragraph_range: {
        start_paragraph_id: `B0001-C0002-P${String(ordinal * 10).padStart(4, "0")}`,
        end_paragraph_id: `B0001-C0002-P${String(ordinal * 10 + 2).padStart(4, "0")}`,
      },
      paragraph_count: role === "beat" ? 2 : 4,
      phase_ordinal: ordinal <= 3 ? 1 : ordinal <= 7 ? 2 : ordinal <= 11 ? 3 : 4,
      role,
      importance_score: role === "core" ? 70 : 45,
      importance_formula_version: "1.1",
      deterministic_reasons: ["e2e"],
      forced_floor_reason: role === "core" && ordinal === 14 ? "chapter_end" : null,
      classification_reasons: ["e2e"],
      final_level: role,
      percentile: role === "core" ? 90 : 40,
      scene_value_summary: `Scene ${ordinal} summary`,
      dominant_emotion: "紧张",
      engagement: { engagement_score: 40 + ordinal * 3 },
      scores: {
        curiosity: 50,
        tension: 50,
        payoff: 50,
        hook: 30 + ordinal * 2,
        information_gain: 45,
        emotional_resonance: 50,
        cognitive_load: 40,
        dropoff_risk: 20,
        valence_start: -5,
        valence_end: 5,
        arousal_start: 30,
        arousal_end: 55,
      },
      reader_question_in: [],
      reader_question_created: ordinal === 1 ? [{ question: "主角能否回家？" }] : [],
      reader_question_answered: [],
      reader_question_out: [{ question: `Q${ordinal}` }],
      payoffs: [],
      hooks:
        ordinal === 14
          ? [
              {
                type: "mystery",
                summary: "章末悬念",
                gap: "未知",
                continue_drive: "强",
                strength: 85,
              },
            ]
          : [],
      techniques: [],
      risk_points: [],
      character_effects: [],
      writing_takeaways: [
        {
          summary: "E2E 写作启示",
          applicable_when: "测试适用",
          avoid_when: "测试慎用",
        },
      ],
      evidence_paragraph_ids: [`B0001-C0002-P${String(ordinal * 10).padStart(4, "0")}`],
      evidence_count: 1,
      confidence: 0.8,
      primary_payoff: null,
      primary_hook:
        ordinal === 14
          ? {
              type: "mystery",
              summary: "章末悬念",
              gap: "未知",
              continue_drive: "强",
              strength: 85,
            }
          : null,
      primary_risk: null,
    };
  });

  const curvePoint = (ordinal: number, value: number) => ({ scene_ordinal: ordinal, value });

  return {
    visualization_version: "1.1",
    chapter_summary: {
      chapter_id: 2,
      chapter_title: "第1章 戏鬼回家",
      diagnosis: "E2E 预测诊断：章末钩子较强。",
      primary_traction: "主角能否安全回家？",
      primary_cluster_title: "主角能否安全回家？",
      core_scene_count: 5,
      strong_hook_count: 2,
      stage_payoff_count: 3,
      max_low_payoff_interval: "Scene 7—8",
      max_fragmentation_interval: "无明显碎片化区间",
      strongest_payoff: {
        scene_ordinal: 8,
        scene_id: 108,
        summary: "阶段兑现",
        strength: 70,
      },
      strongest_hook: { scene_ordinal: 14, scene_id: 114, summary: "章末悬念", strength: 85 },
      weak_interval: "Scene 7—8 (low_engagement)",
      counts: {
        scene_count: 14,
        phase_count: 4,
        question_chain_count: 4,
        canonical_chain_count: 3,
        core: 5,
        secondary: 5,
        beat: 4,
      },
      peaks: {
        engagement_peak: { scene_ordinal: 14, value: 82 },
        engagement_valley: { scene_ordinal: 3, value: 49 },
        engagement_average: 61,
      },
      expanded_diagnosis: {
        chapter_strengths: ["开篇明确"],
        chapter_risks: ["中段偏密"],
      },
    },
    phases: [
      {
        ordinal: 1,
        title: "入局",
        start_scene_ordinal: 1,
        end_scene_ordinal: 3,
        primary_reader_question: "为何回家？",
        dominant_emotion: "不安",
        reading_payoff: "威胁",
        continuation_motivation: "强",
        summary: "建立",
        confidence: 0.8,
        average_engagement: 50,
        core_scene_count: 1,
        beat_count: 1,
        scene_span: 3,
      },
      {
        ordinal: 2,
        title: "推进",
        start_scene_ordinal: 4,
        end_scene_ordinal: 7,
        primary_reader_question: "障碍？",
        dominant_emotion: "紧张",
        reading_payoff: "增量",
        continuation_motivation: "中",
        summary: "升级",
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
        primary_reader_question: "真相？",
        dominant_emotion: "震惊",
        reading_payoff: "反转",
        continuation_motivation: "强",
        summary: "反转",
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
        reading_payoff: "钩子",
        continuation_motivation: "强",
        summary: "悬念",
        confidence: 0.8,
        average_engagement: 75,
        core_scene_count: 2,
        beat_count: 1,
        scene_span: 3,
      },
    ],
    curve_series: {
      engagement: sceneNodes.map((node) =>
        curvePoint(node.scene_ordinal, node.engagement.engagement_score),
      ),
      valence: sceneNodes.map((node) => ({
        scene_ordinal: node.scene_ordinal,
        start: -5,
        end: 5,
      })),
      arousal: sceneNodes.map((node) => ({
        scene_ordinal: node.scene_ordinal,
        start: 30,
        end: 55,
      })),
      curiosity: sceneNodes.map((node) => curvePoint(node.scene_ordinal, 50)),
      tension: sceneNodes.map((node) => curvePoint(node.scene_ordinal, 50)),
      payoff: sceneNodes.map((node) => curvePoint(node.scene_ordinal, 50)),
      hook: sceneNodes.map((node) => curvePoint(node.scene_ordinal, node.scores.hook)),
      dropoff_risk: sceneNodes.map((node) => curvePoint(node.scene_ordinal, 20)),
    },
    scene_nodes: sceneNodes,
    role_counts: { core: 5, secondary: 5, beat: 4 },
    primary_question_chain: {
      canonical_id: "cqc-primary",
      canonical_question: "主角能否安全回家？",
      aliases: [],
      source_chain_ids: ["cqc-primary"],
      created_scene: 1,
      carried_scene_ordinals: [1, 2],
      transformed_scenes: [],
      answered_scene: null,
      status: "carried",
      strength: 70,
      open_at_chapter_end: true,
      confidence: 1,
      merge_reason: "singleton",
      question_type: "goal",
      auto_merged: false,
      lifecycle: [
        { scene_ordinal: 1, status: "created" },
        { scene_ordinal: 2, status: "carried" },
      ],
      importance: 75,
    },
    phase_question_chains: [
      {
        canonical_id: "cqc-phase-2",
        canonical_question: "障碍来自何方？",
        aliases: [],
        source_chain_ids: ["cqc-phase-2"],
        created_scene: 4,
        carried_scene_ordinals: [4, 5],
        transformed_scenes: [],
        answered_scene: null,
        status: "carried",
        strength: 60,
        open_at_chapter_end: true,
        confidence: 1,
        merge_reason: "singleton",
        question_type: "information",
        auto_merged: false,
        lifecycle: [{ scene_ordinal: 4, status: "created" }],
        importance: 55,
      },
    ],
    secondary_question_chains: [
      {
        canonical_id: "cqc-secondary",
        canonical_question: "配角动机是什么？",
        aliases: [],
        source_chain_ids: ["cqc-secondary"],
        created_scene: 6,
        carried_scene_ordinals: [6],
        transformed_scenes: [],
        answered_scene: null,
        status: "open",
        strength: 45,
        open_at_chapter_end: true,
        confidence: 1,
        merge_reason: "singleton",
        question_type: "relationship",
        auto_merged: false,
        lifecycle: [{ scene_ordinal: 6, status: "created" }],
        importance: 40,
      },
    ],
    payoff_markers: [
      {
        scene_ordinal: 4,
        scene_id: 104,
        type: "stage_completion",
        summary: "阶段回报A",
        strength: 66,
      },
      {
        scene_ordinal: 8,
        scene_id: 108,
        type: "information",
        summary: "阶段兑现",
        strength: 70,
      },
      {
        scene_ordinal: 14,
        scene_id: 114,
        type: "horror_payoff",
        summary: "章末回报",
        strength: 80,
      },
    ],
    hook_markers: [
      {
        scene_ordinal: 1,
        scene_id: 101,
        type: "mystery",
        summary: "开篇钩子",
        strength: 90,
      },
      {
        scene_ordinal: 14,
        scene_id: 114,
        type: "mystery",
        summary: "章末悬念",
        strength: 85,
      },
    ],
    all_hook_count: 5,
    visible_hook_count: 2,
    suppressed_hook_count: 3,
    suppressed_hooks: [],
    semantic_payoff_count: 1,
    derived_payoff_count: 4,
    deduped_payoff_count: 4,
    visible_payoff_count: 3,
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
            importance: 55,
            created_scene: 4,
            status: "carried",
          },
        ],
        relationships: [],
        confidence: 0.8,
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
            importance: 55,
            created_scene: 4,
            status: "carried",
          },
        ],
        relationships: [],
        confidence: 0.8,
        merge_reason: "escalation",
        importance: 75,
        created_scene: 1,
        primary_question: "主角能否安全回家？",
      },
    ],
    scene_level_distribution: {
      core: 5,
      secondary: 5,
      beat: 4,
    },
    visual_density_warnings: [],
    risk_intervals: [
      {
        risk_type: "low_engagement",
        start_scene_ordinal: 7,
        end_scene_ordinal: 8,
        span: 2,
        summary: "Scene 7—8 engagement持续偏低",
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
      scene_contract_version: "1.3",
      semantic_source: "model+deterministic_calibration",
      calibrated: true,
    },
  };
}

test.describe("Phase 1C-C.2.1 Reader Journey visual calibration", () => {
  test("renders compact workspace, clusters, marker toggle, and export", async ({ page }) => {
    const visualization = buildVisualizationFixture();

    const scenes = Array.from({ length: 14 }, (_, index) => {
      const ordinal = index + 1;
      const start = `B0001-C0002-P${String(ordinal * 10).padStart(4, "0")}`;
      const end = `B0001-C0002-P${String(ordinal * 10 + 2).padStart(4, "0")}`;
      return {
        scene: {
          id: ordinal,
          scene_key: `B0001-C0002-R0001-S${String(ordinal).padStart(4, "0")}`,
          ordinal,
          start_paragraph_id: start,
          end_paragraph_id: end,
          paragraph_count: 3,
          is_single_paragraph: false,
          boundary_source: "model_accepted",
          boundary_revision_id: 1,
          boundary_detected: true,
          boundary_confidence: 0.9,
        },
        analysis_artifact: {
          id: 100 + ordinal,
          schema_version: "v1",
          prompt_version: "v3.1",
          provider: "fake",
          model: "fake",
          confidence: 0.8,
          validation_status: "valid",
          offline_recovered: false,
          analysis: {
            goal: { summary: `目标-${ordinal}`, evidence_paragraph_ids: [start] },
            outcome: { summary: `结果-${ordinal}`, evidence_paragraph_ids: [end] },
            function_tags: ["事件推进"],
          },
        },
        evidence: [],
        illegal_evidence: [],
        revision: null,
      };
    });

    await page.route("**/api/v1/analysis-runs/55/results", async (route) => {
      await route.fulfill({
        json: {
          run: { id: 55, status: "succeeded", provider: "fake", model: "fake" },
          chapter: { id: 2, title: "第1章 戏鬼回家", display_title: "第1章 戏鬼回家" },
          boundary_revision: { id: 1, revision_number: 1, coverage_rate: 1 },
          summary: { total_scene_count: 14, evidence_coverage_rate: 1 },
          scenes,
        },
      });
    });

    await page.route("**/api/v1/analysis-runs/55/reader-journey", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          json: {
            journey_run_id: 701,
            analysis_run_id: 55,
            status: "succeeded",
            formula_version: "1.0",
            phases: [],
            scene_profiles: [],
            one_sentence_diagnosis: visualization.chapter_summary.diagnosis,
            visualization,
          },
        });
        return;
      }
      await route.fulfill({ status: 405, body: "method not allowed" });
    });

    await page.route("**/reader-journey-runs/701/progress", async (route) => {
      await route.fulfill({
        json: {
          journey_run_id: 701,
          analysis_run_id: 55,
          status: "succeeded",
          total_scene_count: 14,
          completed_scene_count: 14,
          remaining_scene_count: 0,
          phase_count: 4,
          has_chapter_summary: true,
          retryable: false,
        },
      });
    });

    await page.route("**/scenes/*/paragraphs", async (route) => {
      await route.fulfill({ json: { paragraphs: [] } });
    });

    await page.route("**/api/v1/chapters/2/paragraphs**", async (route) => {
      await route.fulfill({
        json: {
          items: Array.from({ length: 80 }, (_, index) => ({
            id: `B0001-C0002-P${String(index + 1).padStart(4, "0")}`,
            chapter_id: 2,
            paragraph_index: index + 1,
            raw_text: `E2E 段落 ${index + 1}`,
          })),
          offset: 0,
          limit: 500,
          total: 80,
          has_more: false,
        },
      });
    });

    await page.goto("/analysis-runs/55/results?tab=reader-journey");
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible();

    await expect(page.getByTestId("journey-sync-title")).toContainText("旅程分析");
    await page.getByTestId("journey-analysis-info").click();
    await expect(page.getByTestId("journey-analysis-info-popover")).toContainText(/visualization v1\.1/);
    await expect(page.getByTestId("journey-marker-compact")).toHaveClass(/active/);
    await expect(page.getByTestId("journey-marker-compact")).toContainText("精简标记");
    await expect(page.getByTestId("journey-phase-strip").locator("button")).toHaveCount(4);
    await expect(page.getByTestId("journey-curve-node-14")).toBeVisible();
    await expect(page.getByTestId("journey-curve-node-14")).toHaveClass(/journey-node-core/);

    const coreNodes = page.locator('[data-testid^="journey-curve-node-"].journey-node-core');
    await expect(coreNodes).toHaveCount(5);

    await expect(page.getByTestId("journey-overview-curve")).toBeVisible();
    await page.getByTestId("journey-curve-node-14").click();
    await expect(page.getByTestId("scene-detail-tab-questions")).toBeVisible();
    await page.getByTestId("scene-detail-tab-questions").click();

    await expect(page.getByTestId("journey-curve-svg")).toBeVisible();
    await page.getByTestId("journey-marker-full").click();
    await expect(page.getByTestId("journey-marker-full")).toHaveClass(/active/);

    await expect(page.getByTestId("journey-detail-drawer")).toContainText("Scene 14");

    await expect(page.getByTestId("journey-export-png")).toBeVisible();
  });
});
