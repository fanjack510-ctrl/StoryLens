import { useMemo } from "react";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import { buildHookPayoffTimelineModel } from "./hookPayoffTimelineModel";

type Props = {
  visualization: ReaderJourneyVisualization;
  selectedLoopId?: string | null;
  selectedSceneOrdinal?: number | null;
  showCandidateRelations?: boolean;
  onSelectLoop?: (loopId: string, sceneOrdinal: number) => void;
};

const KIND_GLYPH: Record<string, string> = {
  new_hook: "●",
  partial: "◐",
  full: "●",
  reversal: "◆",
  transformed: "↗",
  open: "○",
  score_inferred: "◌",
};

/** Dual-rail relationship timeline — NarrativeLoopView only, no dual score curves. */
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

  const width = Math.max(480, model.maxScene * 56 + 80);
  const height = 168;
  const padX = 36;
  const topY = 48;
  const bottomY = 120;
  const xFor = (ordinal: number) =>
    padX + ((ordinal - 1) / Math.max(1, model.maxScene - 1 || 1)) * (width - padX * 2);

  return (
    <div
      className="hook-payoff-timeline"
      data-testid="hook-payoff-timeline"
      data-inconsistent={model.inconsistent ? "true" : "false"}
      data-soft-conflict={model.softConflict ? "true" : "false"}
    >
      <svg
        className="hook-payoff-timeline-svg"
        data-testid="hook-payoff-timeline-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="钩子与回报双轨关系图"
      >
        <text x={8} y={topY + 4} className="hook-payoff-rail-label">
          问题与钩子
        </text>
        <text x={8} y={bottomY + 4} className="hook-payoff-rail-label">
          回应与兑现
        </text>
        <line
          x1={padX}
          y1={topY}
          x2={width - padX}
          y2={topY}
          className="hook-payoff-rail-line"
        />
        <line
          x1={padX}
          y1={bottomY}
          x2={width - padX}
          y2={bottomY}
          className="hook-payoff-rail-line"
        />
        {model.links.map((link) => {
          const from = model.nodes.find((n) => n.id === link.from_id);
          const to = model.nodes.find((n) => n.id === link.to_id);
          if (!from || !to) return null;
          const muted =
            selectedLoopId != null && link.loop_id !== selectedLoopId ? " is-muted" : "";
          return (
            <line
              key={`${link.from_id}->${link.to_id}:${link.grade}`}
              x1={xFor(from.scene_ordinal)}
              y1={topY}
              x2={xFor(to.scene_ordinal)}
              y2={bottomY}
              className={`hook-payoff-link hook-payoff-link--${link.stroke} hook-payoff-link--${link.grade}${muted}`}
              data-testid="hook-payoff-link"
              data-loop-id={link.loop_id}
              data-grade={link.grade}
              data-stroke={link.stroke}
              data-primary={link.is_primary ? "true" : "false"}
            />
          );
        })}
        {model.nodes.map((node) => {
          const y = node.rail === "hook" ? topY : bottomY;
          const x = xFor(node.scene_ordinal);
          const muted = selectedLoopId != null && !node.emphasis ? " is-muted" : "";
          const active = node.emphasis && selectedLoopId === node.loop_id ? " is-active" : "";
          return (
            <g
              key={node.id}
              className={`hook-payoff-node hook-payoff-node--${node.kind}${muted}${active}`}
              data-testid="hook-payoff-node"
              data-loop-id={node.loop_id}
              data-kind={node.kind}
              data-rail={node.rail}
              transform={`translate(${x}, ${y})`}
              onClick={() => onSelectLoop?.(node.loop_id, node.scene_ordinal)}
              style={{ cursor: "pointer" }}
            >
              <title>{node.hover}</title>
              <circle r={node.kind === "open" ? 5 : 7} className="hook-payoff-node-dot" />
              <text y={node.rail === "hook" ? -14 : 18} textAnchor="middle" className="hook-payoff-node-label">
                {KIND_GLYPH[node.kind] || "●"} {node.title}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
