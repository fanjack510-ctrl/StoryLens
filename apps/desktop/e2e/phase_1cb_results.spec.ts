import { expect, test } from "@playwright/test";

/**
 * Phase 1C-B: view completed Scene Analysis results.
 * Fake data via route mocks; never calls real Aliyun.
 * Flow: tasks -> Run #55 -> view results -> auto Scene 01 -> switch Scene 05
 *       -> click P0018 evidence -> highlight -> switch Scene 13 -> P0063
 *       -> overview -> export markdown.
 */

function pid(n: number): string {
  return `B0001-C0002-P${String(n).padStart(4, "0")}`;
}

// ordinal -> [sceneId, startIndex, endIndex, boundary_source, offline]
const SCENES: Record<number, [number, number, number, string | null, boolean]> = {
  1: [6, 1, 12, "user_added", false],
  2: [7, 13, 14, "model_accepted", false],
  3: [8, 15, 15, "user_added", false],
  4: [9, 16, 17, "user_accepted_model_conflict", false],
  5: [10, 18, 18, "user_added", true],
  6: [11, 19, 19, "model_accepted", false],
  7: [12, 20, 28, "model_accepted", false],
  8: [13, 29, 32, "user_accepted_model_conflict", false],
  9: [14, 33, 48, "model_accepted", false],
  10: [15, 49, 56, "model_accepted", false],
  11: [16, 57, 59, "model_accepted", false],
  12: [17, 60, 62, "model_accepted", false],
  13: [18, 63, 63, "user_accepted_model_conflict", true],
  14: [19, 64, 68, null, false],
};

function buildResults() {
  const scenes = Object.entries(SCENES).map(([ord, spec]) => {
    const ordinal = Number(ord);
    const [id, startIdx, endIdx, source, offline] = spec;
    const start = pid(startIdx);
    const end = pid(endIdx);
    return {
      scene: {
        id,
        scene_key: `B0001-C0002-R0001-S${String(ordinal).padStart(4, "0")}`,
        ordinal,
        start_paragraph_id: start,
        end_paragraph_id: end,
        paragraph_count: endIdx - startIdx + 1,
        is_single_paragraph: startIdx === endIdx,
        boundary_source: source,
        boundary_revision_id: 1,
        boundary_detected: true,
        boundary_confidence: 0.9,
      },
      analysis_artifact: {
        id: 8 + ordinal,
        schema_version: "v1",
        prompt_version: "v3.1",
        provider: "aliyun_qwen_plus",
        model: "qwen3.7-plus",
        confidence: 0.8,
        validation_status: "valid",
        created_at: "2026-07-17T07:00:00Z",
        offline_recovered: offline,
        analysis: {
          scene_id: `B0001-C0002-R0001-S${String(ordinal).padStart(4, "0")}`,
          entry_state: { summary: `进入-${ordinal}`, evidence_paragraph_ids: [start] },
          goal: { summary: `目标-${ordinal}`, evidence_paragraph_ids: [start] },
          obstacle: { summary: "", evidence_paragraph_ids: [] },
          key_actions: [{ summary: `动作-${ordinal}`, evidence_paragraph_ids: [start] }],
          turning_point: { summary: "", evidence_paragraph_ids: [] },
          outcome: { summary: `结果-${ordinal}`, evidence_paragraph_ids: [end] },
          unresolved_question: { summary: "", evidence_paragraph_ids: [] },
          function_tags: ["事件推进"],
          confidence: 0.8,
        },
      },
      evidence: [
        { field_path: "entry_state.evidence", group: "entry_state", paragraph_id: start, in_scope: true, order_index: startIdx },
        { field_path: "goal.evidence", group: "goal", paragraph_id: start, in_scope: true, order_index: startIdx },
        { field_path: "outcome.evidence", group: "outcome", paragraph_id: end, in_scope: true, order_index: endIdx },
      ],
      illegal_evidence: [],
      revision: null,
    };
  });
  return {
    run: {
      id: 55,
      status: "succeeded",
      provider: "aliyun_qwen_plus",
      model: "qwen3.7-plus",
      prompt_version: "v3.5",
      schema_version: "v1",
      analysis_mode: "assisted_boundary_review",
      execution_mode: "cloud",
      completed_at: "2026-07-17T07:10:00Z",
    },
    chapter: { id: 2, book_id: 1, chapter_index: 2, title: "第1章 戏鬼回家", display_title: "第1章 戏鬼回家" },
    boundary_revision: { id: 1, revision_number: 1, coverage_rate: 1.0, confirmed_by: "desktop-user", confirmed_at: "2026-07-17T06:00:00Z" },
    summary: {
      total_scene_count: 14,
      coverage_rate: 1.0,
      single_paragraph_scene_count: 4,
      longest_scene_ordinal: 9,
      longest_scene_paragraph_count: 16,
      manual_added_boundary_count: 3,
      model_accepted_boundary_count: 7,
      user_accepted_conflict_count: 3,
      artifact_coverage_rate: 1.0,
      evidence_coverage_rate: 1.0,
      offline_recovered_scene_count: 2,
    },
    scenes,
  };
}

test.describe("Phase 1C-B results viewing", () => {
  test("open Run #55 results and browse scenes", async ({ page }) => {
    const results = buildResults();
    const run55 = {
      id: 55,
      subject_id: "2",
      provider: "aliyun_qwen_plus",
      model: "qwen3.7-plus",
      status: "succeeded",
      progress_current: 14,
      progress_total: 14,
      execution_mode: "cloud",
      cloud_consent: true,
      sends_content_to_cloud: true,
      retryable: false,
      created_at: new Date().toISOString(),
      completed_scene_count: 14,
      total_scene_count: 14,
      reusable_checkpoint_count: 0,
      conflicted_checkpoint_count: 0,
      checkpoint_total_count: 0,
      checkpoint_available: false,
      detection_recovery_available: false,
    };

    await page.route("**/api/v1/analysis-runs", async (route) => {
      await route.fulfill({ json: [run55] });
    });
    await page.route("**/api/v1/analysis-runs/55", async (route) => {
      await route.fulfill({ json: run55 });
    });
    await page.route("**/api/v1/analysis-runs/55/model-invocations", async (route) => {
      await route.fulfill({ json: [] });
    });
    await page.route("**/api/v1/analysis-runs/55/results", async (route) => {
      await route.fulfill({ json: results });
    });
    await page.route("**/api/v1/analysis-runs/55/reader-journey", async (route) => {
      await route.fulfill({ json: null });
    });
    await page.route("**/results/export**", async (route) => {
      await route.fulfill({
        contentType: "text/markdown; charset=utf-8",
        body: "# 分析结果：Run #55 · 第1章 戏鬼回家\n\n- Scene 总数：14\n",
      });
    });
    await page.route("**/api/v1/scenes/*/paragraphs", async (route) => {
      const url = route.request().url();
      const match = url.match(/scenes\/(\d+)\/paragraphs/);
      const sceneId = match ? Number(match[1]) : 0;
      const item = results.scenes.find((s) => s.scene.id === sceneId);
      const scene = item?.scene;
      let paragraphs: { id: string; paragraph_index: number; raw_text: string; in_scene: boolean }[] = [];
      if (scene) {
        paragraphs = [
          { id: scene.start_paragraph_id, paragraph_index: 1, raw_text: `Scene ${scene.ordinal} 起始`, in_scene: true },
        ];
        if (scene.end_paragraph_id !== scene.start_paragraph_id) {
          paragraphs.push({
            id: scene.end_paragraph_id,
            paragraph_index: 2,
            raw_text: `Scene ${scene.ordinal} 结束`,
            in_scene: true,
          });
        }
      }
      await route.fulfill({
        json: {
          scene_id: sceneId,
          scene_key: scene?.scene_key,
          ordinal: scene?.ordinal,
          start_paragraph_id: scene?.start_paragraph_id,
          end_paragraph_id: scene?.end_paragraph_id,
          paragraphs,
        },
      });
    });

    await page.goto("/tasks");
    await page.getByTestId("view-results-55").click();

    // auto Scene 01
    await expect(page.getByTestId("results-header")).toContainText("Run #55 · 14个Scene");
    await expect(page.getByTestId("scene-list-item-1")).toHaveClass(/selected/);
    await expect(page.getByTestId("structure-field-goal")).toContainText("目标-1");

    // switch to Scene 05 (single P0018)
    await page.getByTestId("scene-list-item-5").click();
    await expect(page.getByTestId("structure-field-goal")).toContainText("目标-5");

    // evidence P0018 highlight
    await page.getByTestId("tab-evidence").click();
    await page.getByTestId("evidence-item-B0001-C0002-P0018").first().click();
    await expect(page.getByTestId("paragraph-B0001-C0002-P0018")).toHaveClass(/highlight/);

    // switch to Scene 13 (single P0063)
    await page.getByTestId("scene-list-item-13").click();
    await expect(page.getByTestId("structure-field-goal")).toContainText("目标-13");
    await page.getByTestId("tab-evidence").click();
    await expect(page.getByTestId("evidence-item-B0001-C0002-P0063").first()).toBeVisible();

    // overview
    await page.getByTestId("tab-overview").click();
    await expect(page.getByTestId("overview-panel")).toContainText("Scene总数");
    await expect(page.getByTestId("overview-scene-14")).toBeVisible();

    // export markdown via shell More menu (resident export chrome is hidden)
    await page.getByTestId("results-more-menu-trigger").click();
    const [request] = await Promise.all([
      page.waitForRequest("**/results/export?format=markdown"),
      page.getByTestId("results-more-export-md").click(),
    ]);
    expect(request.url()).toContain("format=markdown");
  });
});
