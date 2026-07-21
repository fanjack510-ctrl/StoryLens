import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef } from "react";
import type { SceneResultItem } from "../../types";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import type { JourneySelectionState } from "../../types/journeySelection";
import { roleLabelZh } from "./journeyUiLabels";
import { PHASE_BAND_COLORS } from "./journeyVisualTokens";

export type ChapterParagraph = {
  id: string;
  paragraph_index: number;
  raw_text: string;
};

export type StructuredChapterTextPaneHandle = {
  scrollToParagraph: (paragraphId: string) => void;
  scrollToScene: (ordinal: number) => void;
};

type Props = {
  chapterTitle: string;
  scenes: SceneResultItem[];
  visualization: ReaderJourneyVisualization;
  paragraphs: ChapterParagraph[];
  selection: JourneySelectionState;
  onSelectScene: (sceneId: number) => void;
  onSelectParagraph: (paragraphId: string, sceneId: number) => void;
  onScrollSpyScene: (ordinal: number) => void;
  isScrollSpySuppressed: () => boolean;
};

function paragraphInRange(
  paragraphId: string,
  startId: string,
  endId: string,
  paragraphs: ChapterParagraph[],
): boolean {
  const index = paragraphs.findIndex((p) => p.id === paragraphId);
  const startIndex = paragraphs.findIndex((p) => p.id === startId);
  const endIndex = paragraphs.findIndex((p) => p.id === endId);
  if (index < 0 || startIndex < 0 || endIndex < 0) return false;
  const lo = Math.min(startIndex, endIndex);
  const hi = Math.max(startIndex, endIndex);
  return index >= lo && index <= hi;
}

function sceneForParagraph(
  paragraphId: string,
  scenes: SceneResultItem[],
  paragraphs: ChapterParagraph[],
): SceneResultItem | undefined {
  return scenes.find((item) =>
    paragraphInRange(
      paragraphId,
      item.scene.start_paragraph_id,
      item.scene.end_paragraph_id,
      paragraphs,
    ),
  );
}

export const StructuredChapterTextPane = forwardRef<StructuredChapterTextPaneHandle, Props>(
  function StructuredChapterTextPane(
    {
      chapterTitle,
      scenes,
      visualization,
      paragraphs,
      selection,
      onSelectScene,
      onSelectParagraph,
      onScrollSpyScene,
      isScrollSpySuppressed,
    },
    ref,
  ) {
    const scrollRef = useRef<HTMLDivElement>(null);

    const nodeByOrdinal = useMemo(() => {
      const map = new Map<number, ReaderJourneyVisualization["scene_nodes"][number]>();
      for (const node of visualization.scene_nodes) {
        map.set(node.scene_ordinal, node);
      }
      return map;
    }, [visualization.scene_nodes]);

    const sceneParagraphGroups = useMemo(() => {
      return scenes.map((item) => {
        const paras = paragraphs.filter((p) =>
          paragraphInRange(
            p.id,
            item.scene.start_paragraph_id,
            item.scene.end_paragraph_id,
            paragraphs,
          ),
        );
        return { sceneItem: item, paragraphs: paras };
      });
    }, [scenes, paragraphs]);

    const scrollToParagraph = useCallback((paragraphId: string) => {
      const node = document.getElementById(`sync-p-${paragraphId}`);
      // Instant jump: smooth scroll often exceeds the 600ms spy lock and lets N-1 rewrite URL.
      node?.scrollIntoView?.({ behavior: "auto", block: "center" });
    }, []);

    const scrollToScene = useCallback(
      (ordinal: number) => {
        const item = scenes.find((s) => s.scene.ordinal === ordinal);
        if (item) scrollToParagraph(item.scene.start_paragraph_id);
      },
      [scenes, scrollToParagraph],
    );

    useImperativeHandle(ref, () => ({ scrollToParagraph, scrollToScene }), [
      scrollToParagraph,
      scrollToScene,
    ]);

    useEffect(() => {
      if (selection.activeParagraphId && selection.selectionSource !== "scroll_spy") {
        scrollToParagraph(selection.activeParagraphId);
      }
    }, [selection.activeParagraphId, selection.selectionSource, scrollToParagraph]);

    const handleScroll = () => {
      if (isScrollSpySuppressed() || !scrollRef.current) return;
      const container = scrollRef.current;
      const centerY = container.scrollTop + container.clientHeight / 2;
      const paragraphEls = container.querySelectorAll<HTMLElement>("[data-paragraph-id]");
      let bestId: string | null = null;
      let bestDistance = Number.POSITIVE_INFINITY;
      paragraphEls.forEach((el) => {
        const paragraphId = el.dataset.paragraphId;
        if (!paragraphId) return;
        const top = el.offsetTop;
        const bottom = top + el.offsetHeight;
        const mid = (top + bottom) / 2;
        const distance = Math.abs(mid - centerY);
        if (distance < bestDistance) {
          bestDistance = distance;
          bestId = paragraphId;
        }
      });
      if (!bestId) return;
      const sceneItem = sceneForParagraph(bestId, scenes, paragraphs);
      if (sceneItem && sceneItem.scene.ordinal !== selection.activeSceneOrdinal) {
        onScrollSpyScene(sceneItem.scene.ordinal);
      }
    };

    const hookOrdinals = new Set(visualization.hook_markers.map((m) => m.scene_ordinal));
    const payoffOrdinals = new Set(visualization.payoff_markers.map((m) => m.scene_ordinal));
    const riskOrdinals = new Set(
      visualization.risk_intervals.flatMap((interval) => {
        const ordinals: number[] = [];
        for (let o = interval.start_scene_ordinal; o <= interval.end_scene_ordinal; o += 1) {
          ordinals.push(o);
        }
        return ordinals;
      }),
    );

    return (
      <div className="structured-chapter-text-pane" data-testid="structured-chapter-text-pane">
        <header className="structured-chapter-head">
          <h2>{chapterTitle}</h2>
        </header>
        <div
          className="structured-chapter-scroll"
          ref={scrollRef}
          onScroll={handleScroll}
          data-testid="structured-chapter-scroll"
        >
          <div className="structured-chapter-body">
            <div className="structure-rail" aria-hidden="true">
              {sceneParagraphGroups.map(({ sceneItem, paragraphs: paras }) => {
                const node = nodeByOrdinal.get(sceneItem.scene.ordinal);
                const phaseIndex = (node?.phase_ordinal ?? 1) - 1;
                const role = node?.role ?? "secondary";
                return (
                  <div
                    key={sceneItem.scene.id}
                    className={`structure-rail-scene structure-rail-${role}`}
                    style={{
                      flexGrow: Math.max(paras.length, 1),
                      background: PHASE_BAND_COLORS[phaseIndex % PHASE_BAND_COLORS.length],
                    }}
                  >
                    <span className={`structure-rail-marker structure-rail-marker-${role}`} />
                    {paras.map((p) => (
                      <span key={p.id} className="structure-rail-tick" />
                    ))}
                  </div>
                );
              })}
            </div>

            <div className="structured-scenes">
              {sceneParagraphGroups.map(({ sceneItem, paragraphs: paras }) => {
                const s = sceneItem.scene;
                const node = nodeByOrdinal.get(s.ordinal);
                const role = node?.role ?? "secondary";
                const phaseOrdinal = node?.phase_ordinal ?? null;
                const isActive = selection.activeSceneOrdinal === s.ordinal;
                const activePhase =
                  selection.activePhaseId ??
                  (selection.activeSceneOrdinal != null
                    ? nodeByOrdinal.get(selection.activeSceneOrdinal)?.phase_ordinal ?? null
                    : null);
                const samePhase =
                  activePhase != null && phaseOrdinal != null && activePhase === phaseOrdinal;
                const dimClass =
                  selection.activeSceneOrdinal == null
                    ? ""
                    : isActive
                      ? "scene-active"
                      : samePhase
                        ? "scene-same-phase"
                        : "scene-other-phase";

                const sceneEvidenceIds =
                  isActive && node?.evidence_paragraph_ids?.length
                    ? node.evidence_paragraph_ids
                    : [];
                const techTitle = `${s.start_paragraph_id} → ${s.end_paragraph_id}`;

                return (
                  <section
                    key={s.id}
                    className={`structured-scene ${dimClass}`}
                    data-scene-id={s.id}
                    data-scene-ordinal={s.ordinal}
                    data-start-paragraph-id={s.start_paragraph_id}
                    data-end-paragraph-id={s.end_paragraph_id}
                    data-display-level={role}
                    data-phase-id={phaseOrdinal ?? undefined}
                  >
                    <button
                      type="button"
                      className="structured-scene-header"
                      data-testid={`structured-scene-header-${s.ordinal}`}
                      title={techTitle}
                      onClick={() => onSelectScene(s.id)}
                    >
                      <span className="structured-scene-ordinal">
                        Scene {s.ordinal}
                      </span>
                      <span className={`structured-scene-role role-${role}`}>
                        {roleLabelZh(role)}
                      </span>
                      {phaseOrdinal != null && (
                        <span className="structured-scene-phase">Phase {phaseOrdinal}</span>
                      )}
                      <span className="structured-scene-range" hidden>
                        {techTitle}
                      </span>
                      <span className="structured-scene-badges">
                        {hookOrdinals.has(s.ordinal) && (
                          <span className="badge-hook" title="钩子标记">
                            钩子
                          </span>
                        )}
                        {payoffOrdinals.has(s.ordinal) && (
                          <span className="badge-payoff" title="回报标记">
                            回报
                          </span>
                        )}
                        {riskOrdinals.has(s.ordinal) && (
                          <span className="badge-risk" title="连续缺少回报、节奏骤降或认知负担过高，可能降低读者继续阅读的意愿。">
                            流失风险
                          </span>
                        )}
                      </span>
                    </button>

                    {paras.map((p) => {
                      const isEvidence =
                        selection.activeEvidenceIds.includes(p.id) ||
                        sceneEvidenceIds.includes(p.id);
                      const isFlash = selection.flashParagraphId === p.id;
                      return (
                        <article
                          key={p.id}
                          id={`sync-p-${p.id}`}
                          data-paragraph-id={p.id}
                          data-scene-id={s.id}
                          data-scene-ordinal={s.ordinal}
                          data-phase-id={phaseOrdinal ?? undefined}
                          data-testid={`sync-paragraph-${p.id}`}
                          className={`structured-paragraph ${isEvidence ? "evidence-mark" : ""} ${
                            isFlash ? "paragraph-flash" : ""
                          } ${selection.activeParagraphId === p.id ? "paragraph-active" : ""}`}
                          onClick={() => onSelectParagraph(p.id, s.id)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              onSelectParagraph(p.id, s.id);
                            }
                          }}
                          role="button"
                          tabIndex={0}
                        >
                          <code className="structured-paragraph-id">{p.id}</code>
                          <p>{p.raw_text}</p>
                        </article>
                      );
                    })}
                  </section>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    );
  },
);
