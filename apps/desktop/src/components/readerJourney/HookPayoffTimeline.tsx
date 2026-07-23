import { useMemo } from "react";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import { buildHookPayoffTimelineModel } from "./hookPayoffTimelineModel";
import { getNarrativeLoops, getReadingResistance } from "./narrativeLoopView";
import { shortPlainTitle } from "./readerJourneyLensExplanation";
import "./hookPayoffTimeline.css";

type Props = {
  visualization: ReaderJourneyVisualization;
  selectedLoopId?: string | null;
  selectedSceneOrdinal?: number | null;
  showCandidateRelations?: boolean;
  onSelectLoop?: (loopId: string, sceneOrdinal: number) => void;
};

const KIND_LABEL: Record<string, string> = {
  new_hook: "钩子",
  partial: "部分回报",
  full: "明确回报",
  reversal: "反转回报",
  transformed: "转化回报",
  open: "等待中",
  score_inferred: "候选",
};

const MAX_VISIBLE_ROWS = 4; // CSS max-height uses this density
const SCENE_COL_MIN = 112;

function truncateLabel(text: string, max = 8): string {
  const t = String(text || "").trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max)}…`;
}

/** One NarrativeLoop per row — readable relationship layout. */
export function HookPayoffTimeline({
  visualization,
  selectedLoopId = null,
  selectedSceneOrdinal = null,
  showCandidateRelations = false,
  onSelectLoop,
}: Props) {
  const model = useMemo(
    () =>
      buildHookPayoffTimelineModel(visualization, {
        selectedLoopId,
        selectedSceneOrdinal,
        showCandidateRelations,
      }),
    [visualization, selectedLoopId, selectedSceneOrdinal, showCandidateRelations],
  );

  const loops = useMemo(() => getNarrativeLoops(visualization), [visualization]);
  const resistanceCount = useMemo(
    () => getReadingResistance(visualization).length,
    [visualization],
  );

  const rows = useMemo(() => {
    return loops
      .filter((loop) => !loop.hard_blocked && loop.consistency_status !== "inconsistent")
      .map((loop) => {
        const nodes = model.nodes.filter((n) => n.loop_id === loop.loop_id);
        const links = model.links.filter((l) => l.loop_id === loop.loop_id && l.is_primary);
        const hook = nodes.find((n) => n.rail === "hook") || nodes[0];
        const payoff = nodes.find((n) => n.rail === "payoff");
        const status = String(loop.display_status || loop.status || "open");
        const statusLabel =
          status === "resolved"
            ? "已回报"
            : status === "partially_resolved"
              ? "部分回报"
              : status === "transformed"
                ? "已转化"
                : status === "abandoned"
                  ? "已放弃"
                  : "仍在等待";
        const emphasis =
          selectedLoopId != null
            ? loop.loop_id === selectedLoopId
            : selectedSceneOrdinal != null
              ? nodes.some((n) => n.scene_ordinal === selectedSceneOrdinal)
              : false;
        return {
          loop,
          hook,
          payoff,
          links,
          statusLabel,
          emphasis,
          shortQ: truncateLabel(shortPlainTitle(loop.question || loop.information_gap || "问题"), 10),
          fullQ: loop.question || loop.information_gap || "",
        };
      });
  }, [loops, model.nodes, model.links, selectedLoopId, selectedSceneOrdinal]);

  const sceneCount = Math.max(model.maxScene, 1);
  const trackMinWidth = Math.max(480, sceneCount * SCENE_COL_MIN + 160);

  return (
    <div
      className="hook-payoff-timeline hook-payoff-timeline--rows"
      data-testid="hook-payoff-timeline"
      data-inconsistent={model.inconsistent ? "true" : "false"}
      data-soft-conflict={model.softConflict ? "true" : "false"}
      data-layout="one-loop-per-row"
      data-max-visible-rows={MAX_VISIBLE_ROWS}
    >
      <div className="hook-payoff-stats" data-testid="hook-payoff-stats">
        <span>建立钩子 {model.stats.established}</span>
        <span>明确回报 {model.stats.answered}</span>
        <span>部分回报 {Math.max(0, model.stats.waiting - model.stats.delayed_risk)}</span>
        <span>仍在等待 {model.stats.waiting}</span>
        <span>阅读阻力 {resistanceCount}</span>
      </div>

      {model.warning ? (
        <p className="hook-payoff-warning" data-testid="hook-payoff-warning">
          {model.warning}
        </p>
      ) : null}

      <div className="hook-payoff-rows-scroll" data-testid="hook-payoff-rows-scroll">
        <div
          className="hook-payoff-rows-track"
          data-testid="hook-payoff-rows-track"
          style={{ minWidth: trackMinWidth }}
        >
          {rows.map((row) => {
            const hookX = row.hook
              ? ((row.hook.scene_ordinal - 1) / Math.max(1, sceneCount - 1)) * 100
              : 0;
            const payoffX = row.payoff
              ? ((row.payoff.scene_ordinal - 1) / Math.max(1, sceneCount - 1)) * 100
              : null;
            const grade = row.links[0]?.grade || "unsupported";
            const stroke = row.links[0]?.stroke || "dotted";
            return (
              <button
                type="button"
                key={row.loop.loop_id}
                className={`hook-payoff-row${row.emphasis ? " is-active" : " is-muted"}`}
                data-testid="hook-payoff-loop-row"
                data-loop-id={row.loop.loop_id}
                data-grade={grade}
                title={row.fullQ}
                onClick={() =>
                  onSelectLoop?.(
                    row.loop.loop_id,
                    row.hook?.scene_ordinal || row.loop.open_from_scene || 1,
                  )
                }
              >
                <span className="hook-payoff-row-question" title={row.fullQ}>
                  {row.shortQ}
                </span>
                <span className="hook-payoff-row-rail">
                  {row.hook ? (
                    <span
                      className="hook-payoff-row-node hook-payoff-row-node--hook"
                      style={{ left: `${hookX}%` }}
                      data-testid="hook-payoff-node"
                      data-kind={row.hook.kind}
                      title={row.hook.hover}
                    >
                      {truncateLabel(row.hook.title, 6)}
                    </span>
                  ) : null}
                  {payoffX != null && row.payoff ? (
                    <>
                      <span
                        className={`hook-payoff-row-link hook-payoff-row-link--${stroke}`}
                        style={{
                          left: `${Math.min(hookX, payoffX)}%`,
                          width: `${Math.abs(payoffX - hookX)}%`,
                        }}
                        data-testid="hook-payoff-link"
                        data-stroke={stroke}
                        data-grade={grade}
                      />
                      <span
                        className="hook-payoff-row-node hook-payoff-row-node--payoff"
                        style={{ left: `${payoffX}%` }}
                        data-testid="hook-payoff-node"
                        data-kind={row.payoff.kind}
                        title={row.payoff.hover}
                      >
                        {KIND_LABEL[row.payoff.kind] || truncateLabel(row.payoff.title, 6)}
                      </span>
                    </>
                  ) : null}
                </span>
                <span className="hook-payoff-row-status">{row.statusLabel}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
