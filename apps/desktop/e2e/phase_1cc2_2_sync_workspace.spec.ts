import { expect, test } from "@playwright/test";

/** Phase 1C-C.2.2 Synchronized Text–Journey Workspace — mocked API, no real cloud. */

function scene14Range() {
  return {
    start: "B0001-C0002-P0064",
    end: "B0001-C0002-P0068",
  };
}

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
    const range =
      ordinal === 14
        ? scene14Range()
        : {
            start: `B0001-C0002-P${String(ordinal * 10).padStart(4, "0")}`,
            end: `B0001-C0002-P${String(ordinal * 10 + 2).padStart(4, "0")}`,
          };
    return {
      scene_id: 100 + ordinal,
      scene_ordinal: ordinal,
      paragraph_range: {
        start_paragraph_id: range.start,
        end_paragraph_id: range.end,
      },
      paragraph_count: ordinal === 14 ? 5 : role === "beat" ? 2 : 4,
      phase_ordinal: ordinal <= 3 ? 1 : ordinal <= 7 ? 2 : ordinal <= 11 ? 3 : 4,
      role,
      importance_score: role === "core" ? 70 : 45,
      importance_formula_version: "1.1",
      deterministic_reasons: ["e2e"],
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
      hooks: ordinal === 14 ? [{ type: "mystery", summary: "章末悬念", strength: 85 }] : [],
      techniques: [],
      risk_points: [],
      character_effects: [],
      writing_takeaways: [
        {
          summary: `Scene ${ordinal} 写作启示`,
          applicable_when: "需要迁移技巧时",
          avoid_when: "信息过载时",
        },
      ],
      evidence_paragraph_ids: [range.start],
      evidence_count: 1,
      confidence: 0.8,
      primary_payoff: null,
      primary_hook:
        ordinal === 14
          ? { type: "mystery", summary: "章末悬念", gap: "未知", continue_drive: "强", strength: 85 }
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
      diagnosis: "E2E 同步工作台诊断。",
      primary_traction: "主角能否安全回家？",
      primary_cluster_title: "主角能否安全回家？",
      core_scene_count: 5,
      strong_hook_count: 2,
      stage_payoff_count: 3,
      max_low_payoff_interval: "Scene 7—8",
      max_fragmentation_interval: "无明显碎片化区间",
      strongest_payoff: { scene_ordinal: 8, scene_id: 108, summary: "阶段兑现", strength: 70 },
      strongest_hook: { scene_ordinal: 14, scene_id: 114, summary: "章末悬念", strength: 85 },
      weak_interval: "Scene 7—8 (low_engagement)",
      counts: { scene_count: 14, phase_count: 4, question_chain_count: 4, canonical_chain_count: 3, core: 5, secondary: 5, beat: 4 },
      peaks: {
        engagement_peak: { scene_ordinal: 14, value: 82 },
        engagement_valley: { scene_ordinal: 3, value: 49 },
        engagement_average: 61,
      },
      expanded_diagnosis: { chapter_strengths: ["开篇明确"], chapter_risks: ["中段偏密"] },
    },
    phases: [
      { ordinal: 1, title: "入局", start_scene_ordinal: 1, end_scene_ordinal: 3, primary_reader_question: "为何回家？", dominant_emotion: "不安", reading_payoff: "威胁", continuation_motivation: "强", summary: "建立", confidence: 0.8, average_engagement: 50, core_scene_count: 1, beat_count: 1, scene_span: 3 },
      { ordinal: 2, title: "推进", start_scene_ordinal: 4, end_scene_ordinal: 7, primary_reader_question: "障碍？", dominant_emotion: "紧张", reading_payoff: "增量", continuation_motivation: "中", summary: "升级", confidence: 0.8, average_engagement: 58, core_scene_count: 1, beat_count: 1, scene_span: 4 },
      { ordinal: 3, title: "转折", start_scene_ordinal: 8, end_scene_ordinal: 11, primary_reader_question: "真相？", dominant_emotion: "震惊", reading_payoff: "反转", continuation_motivation: "强", summary: "反转", confidence: 0.8, average_engagement: 66, core_scene_count: 2, beat_count: 1, scene_span: 4 },
      { ordinal: 4, title: "收束", start_scene_ordinal: 12, end_scene_ordinal: 14, primary_reader_question: "能否脱身？", dominant_emotion: "余悸", reading_payoff: "钩子", continuation_motivation: "强", summary: "悬念", confidence: 0.8, average_engagement: 75, core_scene_count: 2, beat_count: 1, scene_span: 3 },
    ],
    curve_series: {
      engagement: sceneNodes.map((node) => curvePoint(node.scene_ordinal, node.engagement.engagement_score)),
      valence: sceneNodes.map((node) => ({ scene_ordinal: node.scene_ordinal, start: -5, end: 5 })),
      arousal: sceneNodes.map((node) => ({ scene_ordinal: node.scene_ordinal, start: 30, end: 55 })),
      curiosity: sceneNodes.map((node) => curvePoint(node.scene_ordinal, 50)),
      tension: sceneNodes.map((node) => curvePoint(node.scene_ordinal, 50)),
      payoff: sceneNodes.map((node) => curvePoint(node.scene_ordinal, 50)),
      hook: sceneNodes.map((node) => curvePoint(node.scene_ordinal, node.scores.hook)),
      dropoff_risk: sceneNodes.map((node) => curvePoint(node.scene_ordinal, 20)),
    },
    scene_nodes: sceneNodes,
    role_counts: { core: 5, secondary: 5, beat: 4 },
    primary_question_chain: null,
    phase_question_chains: [],
    secondary_question_chains: [],
    payoff_markers: [],
    hook_markers: [{ scene_ordinal: 14, scene_id: 114, type: "mystery", summary: "章末悬念", strength: 85 }],
    all_hook_count: 2,
    visible_hook_count: 1,
    suppressed_hook_count: 1,
    suppressed_hooks: [],
    semantic_payoff_count: 0,
    derived_payoff_count: 0,
    deduped_payoff_count: 0,
    visible_payoff_count: 0,
    question_clusters: [],
    visible_question_clusters: [],
    scene_level_distribution: { core: 5, secondary: 5, beat: 4 },
    visual_density_warnings: [],
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
      scene_contract_version: "1.3",
      semantic_source: "model+deterministic_calibration",
      calibrated: true,
    },
  };
}

function buildScenes() {
  return Array.from({ length: 14 }, (_, index) => {
    const ordinal = index + 1;
    const range =
      ordinal === 14
        ? scene14Range()
        : {
            start: `B0001-C0002-P${String(ordinal * 10).padStart(4, "0")}`,
            end: `B0001-C0002-P${String(ordinal * 10 + 2).padStart(4, "0")}`,
          };
    return {
      scene: {
        id: ordinal,
        scene_key: `B0001-C0002-R0001-S${String(ordinal).padStart(4, "0")}`,
        ordinal,
        start_paragraph_id: range.start,
        end_paragraph_id: range.end,
        paragraph_count: ordinal === 14 ? 5 : 3,
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
          goal: { summary: `目标-${ordinal}`, evidence_paragraph_ids: [range.start] },
          outcome: { summary: `结果-${ordinal}`, evidence_paragraph_ids: [range.end] },
          function_tags: ["事件推进"],
        },
      },
      evidence: [],
      illegal_evidence: [],
      revision: null,
    };
  });
}

function buildChapterParagraphs() {
  return Array.from({ length: 80 }, (_, index) => ({
    id: `B0001-C0002-P${String(index + 1).padStart(4, "0")}`,
    chapter_id: 2,
    paragraph_index: index + 1,
    raw_text: `E2E 段落 ${index + 1}`,
  }));
}

async function mockRun55(page: import("@playwright/test").Page) {
  const visualization = buildVisualizationFixture();
  const scenes = buildScenes();
  const paragraphs = buildChapterParagraphs();

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

  await page.route("**/api/v1/chapters/2/paragraphs**", async (route) => {
    await route.fulfill({
      json: {
        items: paragraphs,
        offset: 0,
        limit: 500,
        total: paragraphs.length,
        has_more: false,
      },
    });
  });

  await page.route("**/scenes/*/paragraphs", async (route) => {
    await route.fulfill({ json: { paragraphs: [] } });
  });
}

test.describe("Phase 1C-C.2.2 Sync workspace", () => {
  test("sync layout, selection sync, URL persistence", async ({ page }) => {
    await mockRun55(page);
    await page.goto("/analysis-runs/55/results?tab=reader-journey&mode=sync&scene=14");

    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible();
    await expect(page.getByTestId("scene-list")).toHaveCount(0);
    await expect(page.getByTestId("journey-split-pane")).toBeVisible();
    await expect(page.getByTestId("structured-chapter-text-pane")).toBeVisible();

    const scene14Section = page.locator('[data-scene-ordinal="14"]');
    await expect(scene14Section.first()).toHaveClass(/scene-active/);

    await expect(page.getByTestId("journey-rhythm-dot-14")).toBeVisible();
    // Prefer text-pane header: rhythm/curve click can race with inspector URL sync on some routes.
    await page.getByTestId("structured-scene-header-14").click();
    await expect(page.getByTestId("sync-paragraph-B0001-C0002-P0064")).toBeVisible();

    await page.getByTestId("scene-detail-tab-evidence").click();
    await page.getByTestId("journey-evidence-B0001-C0002-P0064").click();
    await expect(page.locator(".structured-paragraph.evidence-mark").first()).toBeVisible();

    await page.getByTestId("structured-scene-header-9").click();
    await expect(page.getByTestId("journey-curve-node-9")).toHaveClass(/journey-node-active/);

    await page.getByTestId("journey-phase-3").evaluate((el: HTMLElement) => el.click());
    // v2-2: Phase click must not force Scene to phase start (Scene 8).
    await expect(page.getByTestId("journey-phase-detail-panel")).toBeVisible();
    await expect(page.getByTestId("journey-curve-node-9")).toHaveClass(/journey-node-active/);
    await expect(page.locator('[data-scene-ordinal="9"].scene-active')).toBeVisible();
    await expect(page.locator('[data-scene-ordinal="8"].scene-same-phase')).toBeVisible();
    await expect(page.locator('[data-scene-ordinal="10"].scene-same-phase')).toBeVisible();
    await expect(page.locator('[data-scene-ordinal="11"].scene-same-phase')).toBeVisible();
    await expect(page.locator('[data-scene-ordinal="7"].scene-other-phase')).toBeVisible();

    await page.reload();
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible();
    await expect(page.getByTestId("journey-mode-sync")).toHaveClass(/active/);
    await expect(page.getByTestId("journey-curve-node-9")).toHaveClass(/journey-node-active/);
  });

  test("scene detail drawer renders writing takeaways without crashing", async ({ page }) => {
    await mockRun55(page);
    await page.goto(
      "/analysis-runs/55/results?tab=reader-journey&mode=sync&scene=1&paragraph=B0001-C0002-P0001&metric=engagement",
    );

    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible();
    await expect(page.getByText("Unexpected Application Error!")).toHaveCount(0);
    await expect(page.getByTestId("journey-detail-drawer")).toBeVisible();
    await expect(page.getByTestId("journey-detail-drawer")).toContainText("Scene 1");
    await page.getByTestId("scene-detail-tab-techniques").click();
    await expect(page.getByTestId("journey-writing-takeaways")).toContainText("Scene 1 写作启示");
    await expect(page.getByTestId("journey-writing-takeaways")).toContainText("适用：");
    await expect(page.getByTestId("journey-writing-takeaways")).toContainText("慎用：");

    await expect(page.getByTestId("journey-rhythm-dot-14")).toBeVisible();
    await page.getByTestId("structured-scene-header-14").click();
    await expect(page.getByTestId("scene-detail-title")).toContainText("Scene 14");
    await page.getByTestId("scene-detail-tab-techniques").click();
    await expect(page.getByTestId("journey-writing-takeaways")).toContainText("Scene 14 写作启示");

    await page.getByTestId("scene-detail-tab-evidence").click();
    await page.getByTestId("journey-evidence-B0001-C0002-P0064").click();
    await expect(page.getByTestId("sync-paragraph-B0001-C0002-P0064")).toBeVisible();

    await page.reload();
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible();
    await expect(page.getByTestId("journey-detail-drawer")).toBeVisible();
    await expect(page.getByText("Unexpected Application Error!")).toHaveCount(0);
  });
});
