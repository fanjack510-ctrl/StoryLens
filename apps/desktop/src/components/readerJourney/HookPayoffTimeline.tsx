import { useMemo } from "react";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import {
  buildChapterHookSimplificationModel,
  deriveChapterHookSceneInsightV1,
  hookLabelZh,
  type ChapterHookNodeLabel,
  type ChapterHookSimplificationModel,
} from "./chapterHookSimplification";
import { buildChapterHookVitals } from "./chapterHookVitals";
import {
  buildContiguousStageRuns,
  computeStageBandPixelRanges,
  resolveSceneStageAssignment,
} from "./journeyStageBands";
import "./hookPayoffTimeline.css";

type Props = {
  visualization: ReaderJourneyVisualization;
  presentation?: ChapterHookSimplificationModel | null;
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

function clampInsightLength(text: string, min = 60, max = 140): string {
  const chars = Array.from(text);
  if (chars.length <= max) return text;
  return chars.slice(0, max).join("");
}

const NODE_LABEL_CLASS: Record<ChapterHookNodeLabel, string> = {
  提出疑问: "is-raise",
  加深悬念: "is-deepen",
  给出回应: "is-answer",
  留到下章: "is-carry",
};

/** Ordinary-user hook page — reads single ChapterHookPresentationV1. */
export function HookPayoffTimeline({
  visualization,
  presentation = null,
  selectedLoopId = null,
  selectedSceneOrdinal = null,
  onSelectLoop,
  onSelectScene,
}: Props) {
  const model = useMemo(
    () => presentation ?? buildChapterHookSimplificationModel(visualization),
    [presentation, visualization],
  );
  const hasContent = model.chapter_hook_mode === "reliable";
  const vitals = useMemo(() => buildChapterHookVitals(visualization), [visualization]);
  // Backend-owned wording for the four scene actions (INV-P4). Absent = unconfirmed
  // profile or legacy payload, and then the shipped suspense wording is what shows.
  const vocabulary = visualization.hook_vocabulary ?? null;
  const activeSceneRows = useMemo(
    () => model.scene_rows.filter((row) => row.scene_action !== "none" && row.short_label),
    [model.scene_rows],
  );
  const activeSceneOrdinals = useMemo(
    () => activeSceneRows.map((row) => row.scene_ordinal),
    [activeSceneRows],
  );
  const trackMinWidth = Math.max(280, activeSceneRows.length * SCENE_COL_MIN + 40);

  const stageBands = useMemo(() => {
    if (!activeSceneOrdinals.length || !visualization.phases?.length) return [];
    const assignmentFor = (ordinal: number) =>
      resolveSceneStageAssignment(
        visualization,
        ordinal,
        visualization.scene_nodes.find((n) => n.scene_ordinal === ordinal) ?? null,
      );
    const runs = buildContiguousStageRuns(activeSceneOrdinals, assignmentFor);
    const xFor = (ordinal: number) => lanePercent(ordinal, model.max_scene);
    const pixels = computeStageBandPixelRanges(runs, activeSceneOrdinals, xFor, 0, 100);
    return runs.map((run, index) => ({
      ...run,
      id: `hook-stage-${index}-${run.startSceneOrdinal}`,
      x1: pixels[index]?.x1 ?? 0,
      x2: pixels[index]?.x2 ?? 100,
    }));
  }, [activeSceneOrdinals, visualization, model.max_scene]);

  const sceneInsight = useMemo(() => {
    if (!hasContent || selectedSceneOrdinal == null) return null;
    const node =
      visualization.scene_nodes.find((n) => n.scene_ordinal === selectedSceneOrdinal) ?? null;
    const insight = deriveChapterHookSceneInsightV1({
      visualization,
      sceneOrdinal: selectedSceneOrdinal,
      node,
      presentation: model,
    });
    if (insight.source === "unavailable") return null;
    const body = clampInsightLength(insight.body);
    if (Array.from(body).length < 8) return null;
    return body;
  }, [hasContent, selectedSceneOrdinal, visualization, model]);

  return (
    <div
      className="hook-resolution-panel hook-chapter-simple"
      data-testid="hook-payoff-timeline"
      data-layout="hook-chapter-simple"
      data-empty={model.empty ? "true" : "false"}
      data-empty-kind={model.empty_kind}
      data-chapter-hook-mode={model.chapter_hook_mode}
    >
      <section
        className="hook-resolution-overview"
        data-testid="hook-resolution-overview"
      >
        {/* 单章尺度上钩子真正可测的三件事。回收在这个尺度上量不到（三本书 0/10），
            埋钩量得到，而番茄前三章赌的正是埋钩。 */}
        {vitals.length ? (
          <ul className="hook-chapter-vitals" data-testid="hook-chapter-vitals">
            {vitals.map((vital) => (
              <li
                key={vital.key}
                className="hook-chapter-vital"
                data-testid={`hook-chapter-vital-${vital.key}`}
                data-band={vital.band}
                title={vital.basis}
              >
                <span className="hook-chapter-vital-label">{vital.label}</span>
                <span className="hook-chapter-vital-value">{vital.display}</span>
                <span className="hook-chapter-vital-reading">{vital.reading}</span>
              </li>
            ))}
          </ul>
        ) : null}

        <p className="hook-resolution-verdict" data-testid="hook-resolution-verdict">
          {model.summary_line}
        </p>

        {!hasContent && model.empty_note ? (
          <p className="hook-resolution-empty" data-testid="hook-resolution-empty">
            {model.empty_note}
          </p>
        ) : null}

        {hasContent ? (
          <>
            <section
              className="hook-chapter-reader-questions"
              data-testid="hook-chapter-reader-questions"
            >
              <h3>读者最想知道</h3>
              <ul className="hook-chapter-question-list">
                {model.reader_question_cards.map((card) => (
                  <li
                    key={card.loop_id}
                    className="hook-chapter-question-card"
                    data-testid="hook-chapter-question-card"
                    data-question-status={card.status}
                  >
                    <button
                      type="button"
                      className={
                        selectedLoopId === card.loop_id
                          ? "hook-chapter-question-btn is-active"
                          : "hook-chapter-question-btn"
                      }
                      data-testid="hook-chapter-question-btn"
                      onClick={() => {
                        const hook = model.important_hooks.find(
                          (h) => h.loop_id === card.loop_id,
                        );
                        onSelectLoop?.(
                          card.loop_id,
                          hook?.last_change_scene ||
                            hook?.resolve_scene ||
                            hook?.open_scene ||
                            1,
                        );
                      }}
                    >
                      <span
                        className="hook-chapter-q"
                        data-testid="hook-chapter-question-text"
                        title={card.question_full}
                      >
                        {card.question_full}
                      </span>
                      {/* One line, not three. 状态 is the classification, 轨迹 is where it
                          happened; 角色 was a lookup on 状态 and said the same thing again. */}
                      <span className="hook-chapter-question-line">
                        <span
                          className="hook-chapter-status-pill"
                          data-testid="hook-chapter-question-status"
                          data-status={card.status}
                          title={card.role}
                        >
                          {card.status}
                        </span>
                        <span
                          className="hook-chapter-meta"
                          data-testid="hook-chapter-question-trail"
                        >
                          {card.change_trail}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>

            {activeSceneRows.length ? (
              <div
                className="hook-resolution-bus-scroll hook-chapter-trajectory-scroll"
                data-testid="hook-payoff-rows-scroll"
              >
                <div
                  className="hook-resolution-bus-track hook-chapter-scene-track hook-chapter-trajectory-track"
                  data-testid="hook-payoff-rows-track"
                  style={{ minWidth: trackMinWidth }}
                >
                  {stageBands.length ? (
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
                  ) : null}
                  <div
                    className="hook-chapter-scene-row hook-chapter-trajectory-row"
                    data-testid="hook-chapter-scene-row"
                  >
                    {activeSceneRows.map((row) => {
                      const selected = selectedSceneOrdinal === row.scene_ordinal;
                      const label = row.short_label!;
                      return (
                        <button
                          type="button"
                          key={row.scene_ordinal}
                          className={`hook-chapter-scene-node hook-chapter-trajectory-node${
                            selected ? " is-selected" : ""
                          } ${NODE_LABEL_CLASS[label]}`}
                          data-testid={`hook-chapter-scene-${row.scene_ordinal}`}
                          data-scene-ordinal={row.scene_ordinal}
                          data-hook-node-label={label}
                          data-scene-action={row.scene_action}
                          title={row.full_reason || undefined}
                          onClick={() => {
                            onSelectScene?.(row.scene_ordinal);
                            const related = row.related_hook_ids[0];
                            if (related) onSelectLoop?.(related, row.scene_ordinal);
                          }}
                        >
                          <span className="hook-chapter-scene-id">
                            S{row.scene_ordinal}
                          </span>
                          <span
                            className="hook-chapter-scene-label"
                            data-testid={`hook-chapter-scene-label-${row.scene_ordinal}`}
                            data-canonical-label={label}
                          >
                            {hookLabelZh(label, vocabulary)}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            ) : null}

            {sceneInsight ? (
              <p className="hook-chapter-scene-insight" data-testid="hook-chapter-scene-insight">
                {sceneInsight}
              </p>
            ) : null}
          </>
        ) : null}
      </section>
    </div>
  );
}
