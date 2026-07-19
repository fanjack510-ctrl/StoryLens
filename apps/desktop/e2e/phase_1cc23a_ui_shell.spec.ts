import { test, expect } from "@playwright/test";

const LONG_ZH =
  "这是一段用于验证中文长段落在隐藏段落ID后仍能占满正文列、不会被挤成窄列的测试文本，包含足够多的汉字以便观察换行与宽度，确保阅读体验正常。";

function scene14Range() {
  return { start: "B0001-C0002-P0064", end: "B0001-C0002-P0068" };
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
      diagnosis: "E2E shell 诊断。",
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
      expanded_diagnosis: { chapter_strengths: ["开篇明确"], chapter_risks: ["中段偏密"] },
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
    hook_markers: [
      { scene_ordinal: 14, scene_id: 114, type: "mystery", summary: "章末悬念", strength: 85 },
    ],
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

test.describe("Phase 1C-C.2.3A UI shell", () => {
  test("paragraph ID layout and results single navigation source", async ({ page }) => {
    const visualization = buildVisualizationFixture();
    const scenes = buildScenes();

    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      if (url.includes("/health")) {
        return route.fulfill({
          json: { status: "ok", database: "ok", default_provider: "none" },
        });
      }
      if (url.match(/\/books\/?\d*$/) && route.request().method() === "GET" && !url.includes("chapters")) {
        if (url.endsWith("/books") || url.endsWith("/books/")) {
          return route.fulfill({
            json: [
              {
                id: 1,
                title: "Fixture Novel",
                source_file_name: "fixture.txt",
                source_file_hash: "deadbeefdeadbeef",
                created_at: "2026-01-01T00:00:00Z",
              },
            ],
          });
        }
        return route.fulfill({
          json: {
            id: 1,
            title: "Fixture Novel",
            source_file_name: "fixture.txt",
            source_file_hash: "deadbeefdeadbeef",
            created_at: "2026-01-01T00:00:00Z",
          },
        });
      }
      if (url.includes("/chapters") && !url.includes("paragraphs")) {
        return route.fulfill({
          json: [
            {
              id: 1,
              book_id: 1,
              chapter_index: 0,
              section_type: "front_matter",
              title: "前置内容",
              display_title: "前置内容",
            },
            {
              id: 2,
              book_id: 1,
              chapter_index: 1,
              section_type: "chapter",
              title: "第一章",
              display_title: "第一章",
            },
          ],
        });
      }
      if (url.includes("/paragraphs")) {
        const isChapter2 = url.includes("/chapters/2/");
        return route.fulfill({
          json: {
            items: isChapter2
              ? Array.from({ length: 80 }, (_, index) => ({
                  id: `B0001-C0002-P${String(index + 1).padStart(4, "0")}`,
                  chapter_id: 2,
                  paragraph_index: index + 1,
                  raw_text: index === 63 ? `Scene14 ${LONG_ZH}` : `E2E 段落 ${index + 1}`,
                }))
              : [
                  {
                    id: "B0001-C0001-P0001",
                    raw_text: LONG_ZH,
                    paragraph_index: 1,
                  },
                  {
                    id: "B0001-C0001-P0002",
                    raw_text: "第二段正文。",
                    paragraph_index: 2,
                  },
                ],
            total: isChapter2 ? 80 : 2,
            offset: 0,
            limit: 500,
            has_more: false,
          },
        });
      }
      if (url.includes("/scenes/") && url.includes("/paragraphs")) {
        return route.fulfill({
          json: {
            paragraphs: [
              {
                id: "B0001-C0002-P0064",
                raw_text: LONG_ZH,
                in_scene: true,
              },
            ],
          },
        });
      }
      if (url.includes("/scenes") && !url.includes("paragraphs")) {
        return route.fulfill({ json: [] });
      }
      if (url.includes("/analysis-runs/55/results")) {
        return route.fulfill({
          status: 200,
          json: {
            run: {
              id: 55,
              status: "succeeded",
              provider: "fake",
              model: "fake",
              prompt_version: "v3.5",
              schema_version: "1",
              analysis_mode: "assisted_boundary_review",
              execution_mode: "cloud",
            },
            chapter: {
              id: 2,
              book_id: 1,
              chapter_index: 1,
              title: "第一章",
              display_title: "第一章",
            },
            boundary_revision: { id: 1, revision_number: 1, coverage_rate: 1, confirmed_by: "t" },
            summary: { total_scene_count: 14 },
            scenes,
          },
        });
      }
      if (
        url.includes("/analysis-runs/55/reader-journey") ||
        (url.includes("reader-journey") && !url.includes("preflight"))
      ) {
        return route.fulfill({
          json: {
            journey_run_id: 2,
            analysis_run_id: 55,
            status: "succeeded",
            formula_version: "1.0",
            one_sentence_diagnosis: visualization.chapter_summary.diagnosis,
            visualization,
            phases: [],
            scene_profiles: [],
          },
        });
      }
      if (url.includes("/analysis-runs")) {
        return route.fulfill({ json: [] });
      }
      return route.fulfill({ status: 200, json: {} });
    });

    await page.goto("/library");
    await expect(page.getByTestId("library-page")).toBeVisible();
    await expect(page.getByTestId("primary-nav").getByText("我的书库")).toBeVisible();
    await expect(page.getByTestId("primary-nav").getByText("设置")).toBeVisible();
    await expect(page.getByTestId("primary-nav").getByText("任务中心")).toHaveCount(0);

    await page.getByTestId("dev-nav-toggle").click();
    await expect(page.getByTestId("dev-nav-panel")).toBeVisible();
    await page.getByRole("link", { name: "任务中心" }).click();
    await expect(page).toHaveURL(/\/tasks/);

    // A. Paragraph ID layout on book page
    await page.goto("/books/1");
    await expect(page.getByTestId("book-chapter-shell")).toBeVisible();
    await expect(page.getByTestId("shell-start-analysis")).toBeVisible();
    await expect(page.locator(".book-shell-simplified .analysis-pane")).toBeHidden();

    // Open front matter if listed
    const frontMatter = page.locator(".structure-pane button").filter({ hasText: "前置内容" }).first();
    if (await frontMatter.count()) {
      await frontMatter.click();
    }

    await page.getByTestId("reading-settings-trigger").click();
    await page.getByTestId("reading-show-paragraph-ids").check();
    await expect(page.getByTestId("book-chapter-shell")).toHaveAttribute(
      "data-show-paragraph-ids",
      "true",
    );
    const textWithId = page.locator(".paragraph p").first();
    await expect(textWithId).toBeVisible();
    const wideWithId = await textWithId.evaluate((el) => el.getBoundingClientRect().width);
    expect(wideWithId).toBeGreaterThan(280);

    await page.getByTestId("reading-show-paragraph-ids").uncheck();
    await expect(page.getByTestId("book-chapter-shell")).toHaveAttribute(
      "data-show-paragraph-ids",
      "false",
    );
    const wideHidden = await page
      .locator(".paragraph p")
      .first()
      .evaluate((el) => el.getBoundingClientRect().width);
    expect(wideHidden).toBeGreaterThan(280);

    const chapterBtn = page.locator(".structure-pane button").filter({ hasText: "第一章" }).first();
    if (await chapterBtn.count()) {
      await chapterBtn.click();
      const afterChapter = await page
        .locator(".paragraph p")
        .first()
        .evaluate((el) => el.getBoundingClientRect().width);
      expect(afterChapter).toBeGreaterThan(200);
    }

    // B. Results page — single top nav
    await page.goto("/analysis-runs/55/results");
    await expect(page.getByTestId("results-shell")).toBeVisible();
    await expect(page.getByTestId("back-to-chapter")).toBeVisible();
    await expect(page.getByTestId("result-view-analysis")).toBeVisible();
    await expect(page.getByTestId("result-view-journey")).toBeVisible();
    await expect(page.getByTestId("results-more-menu-trigger")).toBeVisible();

    await expect(page.getByTestId("tab-structure")).toBeVisible();
    await expect(page.getByTestId("tab-evidence")).toBeVisible();
    await expect(page.getByTestId("tab-overview")).toBeVisible();
    await expect(page.getByTestId("tab-history")).toBeHidden();
    await expect(page.getByTestId("tab-journey")).toBeHidden();
    await expect(page.getByTestId("export-json")).toBeHidden();
    await expect(page.getByTestId("export-markdown")).toBeHidden();

    await page.getByTestId("result-view-journey").click();
    await expect(page).toHaveURL(/tab=reader-journey/);
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible();
    await expect(page.getByTestId("journey-mode-sync")).toBeVisible();
    await expect(page.getByTestId("journey-mode-journey")).toBeVisible();
    await expect(page.getByTestId("journey-mode-reading")).toBeVisible();
    await expect(page.locator(".journey-sync-tabs")).toBeHidden();
    await expect(page.locator(".journey-sync-export-bar")).toBeHidden();
    await expect(page.locator(".journey-sync-actions")).toBeHidden();

    // Scene 14 locate via existing curve node (no real model)
    const scene14 = page.getByTestId("journey-curve-node-14");
    if (await scene14.count()) {
      await scene14.click();
      await expect(page.getByTestId("sync-paragraph-B0001-C0002-P0064")).toBeVisible();
    }

    await page.getByTestId("results-more-menu-trigger").click();
    await expect(page.getByTestId("results-more-export-json")).toBeVisible();
    await page.keyboard.press("Escape");
  });
});
