import { useMemo } from "react";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import {
  CHAPTER_HOOK_PAGE_BLURB,
  buildChapterHookSimplificationModel,
  type ChapterHookNodeLabel,
} from "./chapterHookSimplification";
import {
  buildContiguousStageRuns,
  computeStageBandPixelRanges,
  resolveSceneStageAssignment,
} from "./journeyStageBands";
import "./hookPayoffTimeline.css";

type Props = {
  visualization: ReaderJourneyVisualization;
  selectedLoopId?: string | null;
  selectedSceneOrdinal?: number | null;
  onSelectLoop?: (loopId: string, sceneOrdinal: number) => void;
  onSelectScene?: (sceneOrdinal: number) => void;
  onLocateEvidence?: (paragraphId: string) => void;
};

const SCENE_COL_MIN = 72;

function sceneAxis(maxScene: number): number[] {
  return Array.from({ length: maxScene }, (_, i) => i + 1);
}

function lanePercent(scene: number, maxScene: number): number {
  if (maxScene <= 1) return 0;
  return ((scene - 1) / (maxScene - 1)) * 100;
}

const NODE_LABEL_CLASS: Record<ChapterHookNodeLabel, string> = {
  提出疑问: "is-raise",
  加深悬念: "is-deepen",
  给出回应: "is-answer",
  留到下章: "is-carry",
};

/** Ordinary-user hook page: raised / answered / carried / chapter pull + scene labels. */
export function HookPayoffTimeline({
  visualization,
  selectedLoopId = null,
  selectedSceneOrdinal = null,
  onSelectLoop,
  onSelectScene,
}: Props) {
  const model = useMemo(
    () => buildChapterHookSimplificationModel(visualization),
    [visualization],
  );
  const scenes = sceneAxis(model.max_scene);
  const trackMinWidth = Math.max(420, model.max_scene * SCENE_COL_MIN + 40);

  const stageBands = useMemo(() => {
    if (!scenes.length || !(visualization.phases?.length)) return [];
    const assignmentFor = (ordinal: number) =>
      resolveSceneStageAssignment(
        visualization,
        ordinal,
        visualization.scene_nodes.find((n) => n.scene_ordinal === ordinal) ?? null,
      );
    const runs = buildContiguousStageRuns(scenes, assignmentFor);
    const xFor = (ordinal: number) => lanePercent(ordinal, model.max_scene);
    const pixels = computeStageBandPixelRanges(runs, scenes, xFor, 0, 100);
    return runs.map((run, index) => ({
      ...run,
      id: `hook-stage-${index}-${run.startSceneOrdinal}`,
      x1: pixels[index]?.x1 ?? 0,
      x2: pixels[index]?.x2 ?? 100,
    }));
  }, [scenes, visualization, model.max_scene]);

  if (model.empty) {
    return (
      <div
        className="hook-resolution-panel hook-chapter-simple"
        data-testid="hook-payoff-timeline"
        data-layout="hook-chapter-simple"
        data-empty="true"
      >
        <section
          className="hook-resolution-overview"
          data-testid="hook-resolution-overview"
        >
          <p className="hook-chapter-blurb" data-testid="hook-chapter-blurb">
            {CHAPTER_HOOK_PAGE_BLURB}
          </p>
          <p data-testid="hook-resolution-verdict">本章未识别出明确的重要读者问题。</p>
        </section>
        <p className="hook-resolution-empty" data-testid="hook-resolution-empty">
          暂无可用的钩子事实可供展示。
        </p>
      </div>
    );
  }

  return (
    <div
      className="hook-resolution-panel hook-chapter-simple"
      data-testid="hook-payoff-timeline"
      data-layout="hook-chapter-simple"
      data-empty="false"
    >
      <section
        className="hook-resolution-overview"
        data-testid="hook-resolution-overview"
      >
        <p className="hook-chapter-blurb" data-testid="hook-chapter-blurb">
          {CHAPTER_HOOK_PAGE_BLURB}
        </p>
        <p className="hook-resolution-verdict" data-testid="hook-resolution-verdict">
          {model.summary_line}
        </p>
        <ul className="hook-resolution-stats" data-testid="hook-payoff-stats">
          <li data-testid="hook-stat-raised">本章提出：{model.overview.raised} 个重要问题</li>
          <li data-testid="hook-stat-answered">本章回应：{model.overview.answered} 个</li>
          <li data-testid="hook-stat-carried">继续保留：{model.overview.carried} 个</li>
          <li data-testid="hook-stat-chapter-pull">
            章末牵引：{model.overview.chapter_pull}
          </li>
        </ul>

        {model.important_hooks.length ? (
          <div
            className="hook-chapter-important"
            data-testid="hook-chapter-important"
          >
            <h3>本章重要问题</h3>
            <ol className="hook-chapter-important-list">
              {model.important_hooks.map((hook) => (
                <li
                  key={hook.loop_id}
                  data-testid="hook-chapter-important-item"
                  data-loop-id={hook.loop_id}
                  data-hook-role={hook.role}
                >
                  <button
                    type="button"
                    className={
                      selectedLoopId === hook.loop_id
                        ? "hook-chapter-important-btn is-active"
                        : "hook-chapter-important-btn"
                    }
                    onClick={() =>
                      onSelectLoop?.(hook.loop_id, hook.resolve_scene ?? hook.open_scene)
                    }
                  >
                    <span className="hook-chapter-q">{hook.reader_question}</span>
                    <span className="hook-chapter-meta">
                      S{hook.open_scene}
                      {hook.resolve_scene != null ? ` → S${hook.resolve_scene}` : " · 跨章期待"}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        ) : null}

        <div className="hook-resolution-bus-scroll" data-testid="hook-payoff-rows-scroll">
          <div
            className="hook-resolution-bus-track hook-chapter-scene-track"
            data-testid="hook-payoff-rows-track"
            style={{ minWidth: trackMinWidth }}
          >
            <div
              className="hook-chapter-stage-bands"
              data-testid="journey-stage-bands"
              aria-hidden="true"
            >
              {stageBands.map((band) => (
                <div
                  key={band.id}
                  className="hook-resolution-stage-band"
                  data-testid={`journey-stage-band-${band.stageKey}-${band.startSceneOrdinal}`}
                  data-stage-key={band.stageKey}
                  style={{
                    left: `${band.x1}%`,
                    width: `${Math.max(band.x2 - band.x1, 0.5)}%`,
                    background: band.token.chartBand,
                    opacity: 1,
                  }}
                >
                  <span className="hook-resolution-stage-label">{band.label}</span>
                </div>
              ))}
            </div>
            <div
              className="hook-chapter-scene-row"
              data-testid="hook-chapter-scene-row"
            >
              {model.scene_rows.map((row) => {
                const selected = selectedSceneOrdinal === row.scene_ordinal;
                const label = row.short_label;
                return (
                  <button
                    type="button"
                    key={row.scene_ordinal}
                    className={`hook-chapter-scene-node${selected ? " is-selected" : ""}${
                      label ? ` ${NODE_LABEL_CLASS[label]}` : ""
                    }`}
                    data-testid={`hook-chapter-scene-${row.scene_ordinal}`}
                    data-scene-ordinal={row.scene_ordinal}
                    data-hook-node-label={label || undefined}
                    title={row.full_reason || undefined}
                    onClick={() => {
                      onSelectScene?.(row.scene_ordinal);
                      const related = row.related_hook_ids[0];
                      if (related) onSelectLoop?.(related, row.scene_ordinal);
                    }}
                  >
                    <span className="hook-chapter-scene-id">S{row.scene_ordinal}</span>
                    <span
                      className="hook-chapter-scene-label"
                      data-testid={`hook-chapter-scene-label-${row.scene_ordinal}`}
                    >
                      {label || "—"}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
