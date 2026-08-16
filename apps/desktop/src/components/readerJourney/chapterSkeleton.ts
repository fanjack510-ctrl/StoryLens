/**
 * 章节骨架 —— 把一章抽成一张能套到别的稿子上的模板。
 *
 * 拆书 mode was, in its first version, 我在写 read backwards: the same numbers with the
 * annotation moved from the valley to the peak and the heading reworded. That is not a
 * second reading, it is a second wording — and the user said so.
 *
 * What a person deconstructing someone else's chapter actually wants is the structure: how
 * long each move was, what job it did, and in what order. So this derives a *function* for
 * each scene from the numbers rather than restating the model's prose, and states each
 * scene's share of the chapter, because share is the part that transfers. Knowing that a
 * published chapter spends 43% of itself on one opening move is reusable; knowing that its
 * 追读意愿 was 69 is not.
 *
 * Everything here is program-derived from data the page already has — no model call, and
 * nothing invented that the numbers do not support.
 */

import type { JourneySceneNode } from "../../types/readerJourneyVisualization";

export type SkeletonRow = {
  ordinal: number;
  /** Structural job, e.g. 异常开场 / 加压 / 悬置收尾. Generalised, not content-specific. */
  function: string;
  /** Why that label, in the terms that produced it. */
  basis: string;
  paragraphFrom: number | null;
  paragraphTo: number | null;
  paragraphCount: number;
  sharePercent: number;
  /** True when the scene contributes neither a new question nor new information. */
  skippable: boolean;
  isPeak: boolean;
  isValley: boolean;
};

function scoreOf(node: JourneySceneNode, key: string): number | null {
  const raw = (node.scores as Record<string, unknown> | undefined)?.[key];
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function paragraphIndex(id: string | undefined): number | null {
  if (!id) return null;
  // Ids look like B0010-C0002-P0031; the tail is the 1-based paragraph number.
  const match = /P(\d+)\s*$/.exec(id);
  return match ? Number(match[1]) : null;
}

/**
 * Name the move this scene makes.
 *
 * The rules read the same quantities a reader would notice, in the order that decides the
 * label: where the scene sits, whether it raised or answered anything, and how big it is.
 * A scene that matches nothing specific is 推进 — the honest default, not a guess.
 */
function classify(args: {
  node: JourneySceneNode;
  index: number;
  total: number;
  share: number;
  hook: number | null;
  payoff: number | null;
  info: number | null;
  tension: number | null;
  isTensionPeak: boolean;
}): { fn: string; basis: string; skippable: boolean } {
  const { node, index, total, share, hook, payoff, info, tension, isTensionPeak } = args;
  const isFirst = index === 0;
  const isLast = index === total - 1;
  const opens = (hook ?? 0) >= 60;
  const answers = (payoff ?? 0) >= 60;
  const carries = (info ?? 0) >= 55;
  const empty = !opens && !answers && !carries;

  if (isFirst) {
    return opens
      ? { fn: "异常开场", basis: `开篇就抛出问题（钩子 ${Math.round(hook ?? 0)}）`, skippable: false }
      : { fn: "铺垫开场", basis: "开篇先立场景与人物，问题后置", skippable: false };
  }
  if (isLast) {
    // Judged by the ledger, not by the payoff score. A payoff of 65 is level 3 —
    // 「有兑现但强度弱」 — and on a real chapter that ends on 「昨晚杀的是谁」 the raw score
    // read as a close while the ledger went from 6 to 7. What the reader carries out is
    // opened-minus-closed, so that is what names the ending.
    const opened = node.open_questions?.opened ?? null;
    const closed = node.open_questions?.closed ?? null;
    if (opened != null && closed != null) {
      if (opened > closed) {
        return {
          fn: "悬置收尾",
          basis: `章末开 ${opened} 收 ${closed}，把问题留给下一章`,
          skippable: false,
        };
      }
      if (closed > opened) {
        return {
          fn: "闭合收尾",
          basis: `章末开 ${opened} 收 ${closed}，欠账在这里还上了`,
          skippable: false,
        };
      }
      return opens
        ? { fn: "余味收尾", basis: `章末开 ${opened} 收 ${closed}，不留悬置但留惦记`, skippable: false }
        : { fn: "平收", basis: "章末既未抛出也未回应", skippable: false };
    }
    if (opens && !answers) {
      return { fn: "悬置收尾", basis: "章末抛出新问题而不作答", skippable: false };
    }
    return answers
      ? { fn: "闭合收尾", basis: `章末给出回应（兑现 ${Math.round(payoff ?? 0)}）`, skippable: false }
      : { fn: "平收", basis: "章末既未抛出也未回应", skippable: false };
  }
  if (empty && share <= 12) {
    return {
      fn: "换气",
      basis: `${share.toFixed(0)}% 篇幅，无新问题无新信息——短则是节奏留白，长则是水`,
      skippable: true,
    };
  }
  if (empty) {
    return {
      fn: "空转",
      basis: `占 ${share.toFixed(0)}% 却无新问题无新信息`,
      skippable: true,
    };
  }
  if (isTensionPeak && (tension ?? 0) >= 60) {
    return { fn: "压力峰值", basis: `全章张力最高（${Math.round(tension ?? 0)}）`, skippable: false };
  }
  if (opens && !answers) {
    return { fn: "加压", basis: `又开一个问题而不作答（钩子 ${Math.round(hook ?? 0)}）`, skippable: false };
  }
  if (answers && !opens) {
    return { fn: "兑现", basis: `回应了先前的悬置（兑现 ${Math.round(payoff ?? 0)}）`, skippable: false };
  }
  if (carries) {
    return { fn: "信息投放", basis: `本场的主要贡献是新信息（${Math.round(info ?? 0)}）`, skippable: false };
  }
  return { fn: "推进", basis: "有推进但没有单一的主导动作", skippable: false };
}

export function buildChapterSkeleton(nodes: JourneySceneNode[]): SkeletonRow[] {
  const rows = nodes
    .filter((n) => n.include_in_main_curve !== false)
    .slice()
    .sort((a, b) => a.scene_ordinal - b.scene_ordinal);
  if (rows.length < 2) return [];

  const totalParas = rows.reduce((sum, n) => sum + (Number(n.paragraph_count) || 0), 0);
  const mains = rows.map((n) => scoreOf(n, "reading_momentum"));
  const finite = mains.filter((v): v is number => v != null);
  const peak = finite.length ? Math.max(...finite) : null;
  const valley = finite.length ? Math.min(...finite) : null;
  const tensions = rows.map((n) => scoreOf(n, "tension"));
  const tensionPeak = tensions.filter((v): v is number => v != null);
  const maxTension = tensionPeak.length ? Math.max(...tensionPeak) : null;

  return rows.map((node, index) => {
    const count = Number(node.paragraph_count) || 0;
    const share = totalParas ? (count / totalParas) * 100 : 0;
    const tension = tensions[index];
    const { fn, basis, skippable } = classify({
      node,
      index,
      total: rows.length,
      share,
      hook: scoreOf(node, "hook"),
      payoff: scoreOf(node, "payoff"),
      info: scoreOf(node, "information_gain"),
      tension,
      isTensionPeak: maxTension != null && tension === maxTension,
    });
    return {
      ordinal: node.scene_ordinal,
      function: fn,
      basis,
      paragraphFrom: paragraphIndex(node.paragraph_range?.start_paragraph_id),
      paragraphTo: paragraphIndex(node.paragraph_range?.end_paragraph_id),
      paragraphCount: count,
      sharePercent: share,
      skippable,
      isPeak: peak != null && mains[index] === peak,
      isValley: valley != null && mains[index] === valley,
    };
  });
}

/**
 * One line naming what the chapter does with the reader's questions overall.
 *
 * The per-scene rows say what each move was; this says what the sequence adds up to, which
 * is the part a 拆书 reader copies. Derived from the ledger the chapter already carries.
 */
export function skeletonLedgerNote(nodes: JourneySceneNode[]): string | null {
  const rows = nodes
    .filter((n) => n.open_questions && n.include_in_main_curve !== false)
    .sort((a, b) => a.scene_ordinal - b.scene_ordinal);
  if (rows.length < 2) return null;
  const opened = rows.reduce((s, n) => s + (n.open_questions?.opened ?? 0), 0);
  const closed = rows.reduce((s, n) => s + (n.open_questions?.closed ?? 0), 0);
  const end = rows[rows.length - 1].open_questions?.balance ?? 0;
  if (end === 0) {
    return `全章开 ${opened} 收 ${closed}，走到章末一分不欠——读者没有非追不可的理由，靠的是余味。`;
  }
  return `全章开 ${opened} 收 ${closed}，章末仍欠 ${end} 个未答——这一章的动力来自赊账，不是来自兑现。`;
}
