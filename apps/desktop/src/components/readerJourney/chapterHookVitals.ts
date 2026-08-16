/**
 * 单章尺度上钩子真正可测的三件事。
 *
 * The lens was called 钩子回收 and led with three 读者最想知道 cards. Measured on three real
 * books, 0 of 10 hooks were ever answered inside the chapter — not because chapters are
 * short, but because `v2_profile_to_v1_compat_payload` hardcoded `payoffs: []`. The 回收
 * half could not fire on any input, so all three cards always read 新提出 · 留到下章 and the
 * panel had no variance to show.
 *
 * What a chapter CAN say, and what a 番茄 opening lives or dies on, is where the hooks are
 * buried: how hard the first scene pulls, where the first one lands, and how hard the last
 * scene pulls the reader into the next chapter. Those three separate the same three books
 * cleanly — first-scene hook 95 / 50 / 50 — where the four-label vocabulary separated
 * nothing.
 *
 * Everything here is derived from data the page already holds. No model call.
 */

import type {
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";

export type HookVital = {
  key: "opening" | "ending" | "first_hook";
  label: string;
  /** 0–100 where the vital is a score; null when it is a position or is unavailable. */
  score: number | null;
  /**
   * What to print big. A position is not a score, but it is still the number this row
   * exists to report — printing 「—」 and hiding 「第 2 段」 in a tooltip loses the one fact
   * a 番茄 opening is judged on.
   */
  display: string;
  /** What the number says, in one clause. */
  reading: string;
  /** Where it came from, so a reader can check it. */
  basis: string;
  /** Coarse banding for colour. Never invented when the number is missing. */
  band: "strong" | "ok" | "weak" | "unknown";
};

function scoreOf(node: JourneySceneNode | undefined, key: string): number | null {
  if (!node) return null;
  const raw = (node.scores as Record<string, unknown> | undefined)?.[key];
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function paragraphNumber(id: string | null | undefined): number | null {
  if (!id) return null;
  const match = /P(\d+)\s*$/.exec(String(id));
  return match ? Number(match[1]) : null;
}

function bandOf(score: number | null): HookVital["band"] {
  if (score == null) return "unknown";
  if (score >= 75) return "strong";
  if (score >= 55) return "ok";
  return "weak";
}

function mainScenes(visualization: ReaderJourneyVisualization): JourneySceneNode[] {
  return (visualization.scene_nodes || [])
    .filter((node) => node.include_in_main_curve !== false)
    .slice()
    .sort((a, b) => a.scene_ordinal - b.scene_ordinal);
}

/**
 * Where the chapter's first hook lands, as a paragraph number and a share of the chapter.
 *
 * Reads `first_hook_paragraph_id` when the artifact carries it (prompt v2.2). Before that
 * the position existed only in prose — the model wrote 「第一个钩子出现在第10段」 while the
 * structured field pointed at the scene's own first paragraph on all three books — so a
 * pre-v2.2 artifact returns null rather than a number that disagrees with its own text.
 */
export function firstHookPosition(visualization: ReaderJourneyVisualization): {
  paragraph: number | null;
  sharePercent: number | null;
  totalParagraphs: number;
} {
  const scenes = mainScenes(visualization);
  const total = scenes.reduce((sum, n) => sum + (Number(n.paragraph_count) || 0), 0);
  for (const node of scenes) {
    const hook = (node.hooks || [])[0];
    const paragraph = paragraphNumber(hook?.evidence_paragraph_ids?.[0]);
    if (paragraph != null) {
      return {
        paragraph,
        sharePercent: total ? (paragraph / total) * 100 : null,
        totalParagraphs: total,
      };
    }
  }
  return { paragraph: null, sharePercent: null, totalParagraphs: total };
}

/**
 * The three vitals, in the order a reader should read them.
 *
 * Returns [] when there are no scenes to measure. A vital whose number is missing is still
 * returned, with band "unknown" and a basis saying so — a silently absent row reads as
 * "fine", which is the one thing it must not read as.
 */
export function buildChapterHookVitals(
  visualization: ReaderJourneyVisualization,
): HookVital[] {
  const scenes = mainScenes(visualization);
  if (!scenes.length) return [];

  const first = scenes[0];
  const last = scenes[scenes.length - 1];
  const openingScore = scoreOf(first, "hook");
  const endingScore = scoreOf(last, "hook");
  const ledger = last.open_questions ?? null;
  const position = firstHookPosition(visualization);

  const openingReading =
    openingScore == null
      ? "本场未给出钩子强度"
      : openingScore >= 75
        ? "开篇就抓住了"
        : openingScore >= 55
          ? "开篇有拉力，但不算强"
          : "开篇拉力不足";

  const endingReading =
    endingScore == null
      ? "章末未给出钩子强度"
      : endingScore >= 75
        ? "章末拉得住，读者有理由翻页"
        : endingScore >= 55
          ? "章末有牵引，但不够硬"
          : "章末几乎没有往下拉";

  const ledgerBasis =
    ledger && typeof ledger.opened === "number" && typeof ledger.closed === "number"
      ? `本章开 ${ledger.opened} 收 ${ledger.closed}，走到章末仍欠 ${ledger.balance ?? 0}`
      : "本章未记录未答问题账本";

  const positionReading =
    position.paragraph == null
      ? "本次分析未记录首钩位置"
      : position.sharePercent != null && position.sharePercent <= 15
        ? "第一段就下钩"
        : position.sharePercent != null && position.sharePercent <= 35
          ? "钩子来得不算晚"
          : "钩子来得偏晚";

  return [
    {
      key: "opening",
      label: "开篇抓力",
      score: openingScore,
      display: openingScore == null ? "—" : String(Math.round(openingScore)),
      reading: openingReading,
      basis: `首场 S${first.scene_ordinal} 的钩子强度`,
      band: bandOf(openingScore),
    },
    {
      key: "ending",
      label: "章末牵引",
      score: endingScore,
      display: endingScore == null ? "—" : String(Math.round(endingScore)),
      reading: endingReading,
      basis: ledgerBasis,
      band: bandOf(endingScore),
    },
    {
      key: "first_hook",
      // Backend-owned, same rule as the four actions: 「首钩」 is the suspense word for it.
      label: visualization.hook_vocabulary?.first_mark || "首钩位置",
      score: null,
      display: position.paragraph == null ? "—" : `P${position.paragraph}`,
      reading: positionReading,
      basis:
        position.paragraph == null
          ? "首钩位置需要 v2.2 及以后的分析结果"
          : `第 ${position.paragraph} 段，全章共 ${position.totalParagraphs} 段` +
            (position.sharePercent != null
              ? `（前 ${position.sharePercent.toFixed(0)}%）`
              : ""),
      // A position is not a score, so it gets no score band. Whether P10 of 15 is late
      // depends on the chapter, and the reading above already says which side it falls on.
      band: position.paragraph == null ? "unknown" : "ok",
    },
  ];
}
