/**
 * Live Hook Rich presentation precheck against running MG API.
 * Run from repo root:
 *   npx tsx release/evidence/hotfix/1.1.2/CHG-20260729-011/precheck_hook_rich_presentation.ts
 */
import { writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { buildChapterHookSimplificationModel } from "../../../../../apps/desktop/src/components/readerJourney/chapterHookSimplification.ts";

const __dirname = dirname(fileURLToPath(import.meta.url));
const API = process.env.MG_API || "http://127.0.0.1:18047";
const JOURNEY_ID = Number(process.env.HOOK_RICH_JOURNEY_ID || "5");
const OUT = resolve(__dirname, "HOOK_RICH_PRESENTATION_PRECHECK.json");

async function main() {
  const resp = await fetch(`${API}/api/v1/reader-journeys/${JOURNEY_ID}`);
  if (!resp.ok) throw new Error(`journey HTTP ${resp.status}`);
  const body = await resp.json();
  if (body.status !== "succeeded" || !body.visualization) {
    throw new Error("missing succeeded visualization");
  }
  const model = buildChapterHookSimplificationModel(body.visualization);
  const trajectory = model.scene_rows.filter((r) => r.scene_action !== "none");
  const checks = {
    verdict_count: model.summary_line ? 1 : 0,
    card_count: model.important_hooks.length,
    trajectory_nodes: trajectory.length,
    has_raise: trajectory.some((r) => r.scene_action === "raise"),
    has_deepen: trajectory.some((r) => r.scene_action === "deepen"),
    has_respond: trajectory.some((r) => r.scene_action === "respond"),
    has_carry: trajectory.some((r) => r.scene_action === "carry"),
    empty: model.empty,
    mode: model.chapter_hook_mode,
    summary_line: model.summary_line,
    questions: model.important_hooks.map((h) => ({
      q: h.reader_question,
      result: h.result_label,
    })),
    trajectory_labels: trajectory.map((r) => ({
      scene: r.scene_ordinal,
      action: r.scene_action,
      label: r.short_label,
    })),
  };
  const pass =
    checks.verdict_count === 1 &&
    checks.card_count >= 1 &&
    checks.card_count <= 3 &&
    checks.trajectory_nodes >= 1 &&
    checks.has_raise &&
    checks.has_deepen &&
    (checks.has_respond || checks.has_carry) &&
    !checks.empty &&
    checks.mode === "reliable";

  const out = { pass, journey_id: JOURNEY_ID, checks };
  writeFileSync(OUT, JSON.stringify(out, null, 2) + "\n", "utf-8");
  console.log(JSON.stringify(out, null, 2));
  if (!pass) process.exit(1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
