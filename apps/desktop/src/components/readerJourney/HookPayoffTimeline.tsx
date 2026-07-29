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
import { useDeveloperModeStore } from "../../stores/developerModeStore";
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

/** Ordinary-user hook page (CHG-005 complete). */
export function HookPayoffTimeline({
  visualization,
  selectedLoopId = null,
  selectedSceneOrdinal = null,
  onSelectLoop,
  onSelectScene,
}: Props) {
  const developerMode = useDeveloperModeStore((s) => s.developerMode);
  const model = useMemo(
    () => buildChapterHookSimplificationModel(visualization),
    [visualization],
  );
  const scenes = model.scene_rows.map((r) => r.scene_ordinal);
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

  return (
    <div
      className="hook-resolution-panel hook-chapter-simple"
      data-testid="hook-payoff-timeline"
      data-layout="hook-chapter-simple"
      data-empty={model.empty ? "true" : "false"}
      data-empty-kind={model.empty_kind}
    >
      <section
        className="hook-resolution-overview"
        data-testid="hook-resolution-overview"
      >
        <p className="hook-chapter-blurb" data-testid="hook-chapter-blurb">
          {CHAPTER_HOOK_PAGE_BLURB}
        </p>

        {model.empty ? (
          <>
            <p className="hook-resolution-verdict" data-testid="hook-resolution-verdict">
              {model.empty_title}
            </p>
            <p className="hook-resolution-empty" data-testid="hook-resolution-empty">
              {model.empty_note}
            </p>
          </>
        ) : (
          <>
            <p className="hook-resolution-verdict" data-testid="hook-resolution-verdict">
              {model.summary_line}
            </p>
            <ul className="hook-resolution-stats" data-testid="hook-payoff-stats">
              <li data-testid="hook-stat-raised">
                本章提出：{model.overview.raised} 个重要问题
              </li>
              <li data-testid="hook-stat-answered">
                本章回应：{model.overview.answered} 个
              </li>
              <li data-testid="hook-stat-carried">
                继续保留：{model.overview.carried} 个
              </li>
              <li data-testid="hook-stat-chapter-pull">
                章末牵引：{model.overview.chapter_pull}
              </li>
            </ul>

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
                <div className="hook-chapter-scene-row" data-testid="hook-chapter-scene-row">
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
                      data-hook-result={hook.result_label}
                    >
                      <button
                        type="button"
                        className={
                          selectedLoopId === hook.loop_id
                            ? "hook-chapter-important-btn is-active"
                            : "hook-chapter-important-btn"
                        }
                        onClick={() =>
                          onSelectLoop?.(
                            hook.loop_id,
                            hook.last_change_scene || hook.resolve_scene || hook.open_scene,
                          )
                        }
                      >
                        <span className="hook-chapter-q">{hook.reader_question}</span>
                        <span className="hook-chapter-meta">
                          提出：S{hook.open_scene}
                        </span>
                        <span className="hook-chapter-meta">
                          结果：{hook.result_label}
                        </span>
                        <span className="hook-chapter-meta">
                          最后变化：S{hook.last_change_scene}
                        </span>
                      </button>
                    </li>
                  ))}
                </ol>
              </div>
            ) : null}

            <section
              className="hook-chapter-ending-pull"
              data-testid="hook-chapter-ending-pull"
              data-pull-status={model.ending_pull.status}
            >
              <h3>章末牵引</h3>
              {model.ending_pull.left_behind ? (
                <p data-testid="hook-ending-left">{model.ending_pull.left_behind}</p>
              ) : null}
              {model.ending_pull.reader_wants ? (
                <p data-testid="hook-ending-wants">{model.ending_pull.reader_wants}</p>
              ) : null}
              <p data-testid="hook-ending-judgment">
                判断：{model.ending_pull.judgment || "暂无可靠判断"}
              </p>
              <p className="hook-chapter-meta" data-testid="hook-ending-status">
                状态：{model.ending_pull.status}
              </p>
            </section>
          </>
        )}
      </section>

      {developerMode ? (
        <details
          className="hook-chapter-tech-details"
          data-testid="hook-chapter-tech-details"
        >
          <summary>技术详情</summary>
          <div className="hook-chapter-tech-table-wrap">
            <table className="hook-chapter-tech-table" data-testid="hook-chapter-tech-table">
              <thead>
                <tr>
                  <th>Hook ID</th>
                  <th>问题</th>
                  <th>状态</th>
                  <th>提出</th>
                  <th>强化</th>
                  <th>回应</th>
                  <th>冲突</th>
                  <th>证据数</th>
                  <th>source</th>
                  <th>confidence</th>
                </tr>
              </thead>
              <tbody>
                {model.tech_rows.map((row) => (
                  <tr key={row.loop_id} data-testid="hook-chapter-tech-row">
                    <td>{row.loop_id}</td>
                    <td>{row.question}</td>
                    <td>{row.status}</td>
                    <td>S{row.open_scene}</td>
                    <td>
                      {row.development_scenes.length
                        ? row.development_scenes.map((s) => `S${s}`).join(",")
                        : "—"}
                    </td>
                    <td>
                      {row.resolve_scene != null
                        ? `S${row.resolve_scene} (${row.payoff_types.join("/") || "—"})`
                        : "—"}
                    </td>
                    <td>{row.has_conflict ? "有" : "无"}</td>
                    <td>{row.evidence_count}</td>
                    <td>{row.source}</td>
                    <td>{row.confidence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
    </div>
  );
}
