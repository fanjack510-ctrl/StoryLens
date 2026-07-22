import { useEffect, useMemo, useRef, useState } from "react";
import type { Chapter } from "../../types";
import {
  bodyChapters,
  bodyOrdinalOf,
  buildChapterRanges,
  chapterListLabel,
  chaptersInRange,
  frontMatterChapters,
  rangeContainingOrdinal,
  type ChapterRange,
} from "../../services/chapterNavigation";

type Props = {
  chapters: Chapter[];
  currentChapterId: number;
  onSelect: (chapterId: number) => void;
  listRef?: React.RefObject<HTMLDivElement | null>;
};

export function ChapterListViewport({
  chapters,
  currentChapterId,
  onSelect,
  listRef: externalRef,
}: Props) {
  const internalRef = useRef<HTMLDivElement>(null);
  const listRef = externalRef || internalRef;
  const body = useMemo(() => bodyChapters(chapters), [chapters]);
  const front = useMemo(() => frontMatterChapters(chapters), [chapters]);
  const ranges = useMemo(() => buildChapterRanges(body.length), [body.length]);
  const currentOrdinal = bodyOrdinalOf(chapters, currentChapterId);
  const [activeRange, setActiveRange] = useState<ChapterRange | null>(() =>
    rangeContainingOrdinal(ranges, currentOrdinal),
  );

  useEffect(() => {
    setActiveRange(rangeContainingOrdinal(ranges, currentOrdinal));
  }, [ranges, currentOrdinal]);

  const visible = chaptersInRange(chapters, activeRange || ranges[0] || null);

  useEffect(() => {
    const root = listRef.current;
    if (!root || !currentChapterId) return;
    const el = root.querySelector<HTMLElement>(
      `.workspace-chapter-item[data-chapter-id="${currentChapterId}"]`,
    );
    el?.scrollIntoView({ block: "center", inline: "nearest" });
  }, [currentChapterId, activeRange, listRef, visible.length]);

  if (!chapters.length) {
    return (
      <div className="workspace-chapter-viewport" data-testid="workspace-chapter-viewport">
        <p className="workspace-chapter-empty" data-testid="workspace-chapter-empty">
          尚未识别到章节
        </p>
      </div>
    );
  }

  return (
    <div className="workspace-chapter-viewport" data-testid="workspace-chapter-viewport">
      {ranges.length > 1 ? (
        <div className="workspace-chapter-ranges" data-testid="workspace-sidebar-ranges">
          <select
            aria-label="章节区间"
            data-testid="workspace-sidebar-range-select"
            value={
              activeRange
                ? `${activeRange.startOrdinal}-${activeRange.endOrdinal}`
                : ""
            }
            onChange={(e) => {
              const [start, end] = e.target.value.split("-").map(Number);
              const next = ranges.find(
                (r) => r.startOrdinal === start && r.endOrdinal === end,
              );
              if (next) setActiveRange(next);
            }}
          >
            {ranges.map((r) => (
              <option key={r.label} value={`${r.startOrdinal}-${r.endOrdinal}`}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      <div className="workspace-chapter-list" ref={listRef} data-testid="workspace-chapter-list">
        {front.map((c) => {
          const title = c.display_title || c.title;
          return (
            <button
              type="button"
              className={`workspace-chapter-item${currentChapterId === c.id ? " selected" : ""}`}
              data-chapter-id={c.id}
              onClick={() => onSelect(c.id)}
              key={`front-${c.id}`}
              title={title}
            >
              <span className="workspace-chapter-num">{chapterListLabel(c)}</span>
              <span className="workspace-chapter-title">{title}</span>
            </button>
          );
        })}
        {visible.map((c) => {
          const title = c.display_title || c.title;
          const ordinal = bodyOrdinalOf(chapters, c.id);
          return (
            <button
              type="button"
              className={`workspace-chapter-item${currentChapterId === c.id ? " selected" : ""}`}
              data-chapter-id={c.id}
              onClick={() => onSelect(c.id)}
              key={c.id}
              title={title}
            >
              <span className="workspace-chapter-num">{chapterListLabel(c, ordinal)}</span>
              <span className="workspace-chapter-title">{title}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
