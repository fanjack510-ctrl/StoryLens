import { useEffect, useMemo, useRef, useState } from "react";
import type { Chapter } from "../../types";
import {
  bodyChapters,
  bodyOrdinalOf,
  buildChapterRanges,
  chapterListLabel,
  chaptersInRange,
  filterChaptersByTitle,
  rangeContainingOrdinal,
  resolveOrdinalJump,
  type ChapterRange,
} from "../../services/chapterNavigation";
import "./chapterNavigator.css";

type Props = {
  open: boolean;
  bookTitle: string;
  chapters: Chapter[];
  currentChapterId: number | null;
  onClose: () => void;
  onSelectChapter: (chapterId: number) => void;
};

export function ChapterNavigatorDrawer({
  open,
  bookTitle,
  chapters,
  currentChapterId,
  onClose,
  onSelectChapter,
}: Props) {
  const body = useMemo(() => bodyChapters(chapters), [chapters]);
  const total = body.length;
  const ranges = useMemo(() => buildChapterRanges(total), [total]);
  const currentOrdinal = bodyOrdinalOf(chapters, currentChapterId);
  const [query, setQuery] = useState("");
  const [ordinalInput, setOrdinalInput] = useState("");
  const [ordinalError, setOrdinalError] = useState<string | null>(null);
  const [activeRange, setActiveRange] = useState<ChapterRange | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setOrdinalInput(currentOrdinal ? String(currentOrdinal) : "");
    setOrdinalError(null);
    setActiveRange(rangeContainingOrdinal(ranges, currentOrdinal));
    const t = window.setTimeout(() => searchRef.current?.focus(), 50);
    return () => window.clearTimeout(t);
  }, [open, ranges, currentOrdinal]);

  useEffect(() => {
    if (!open || query.trim()) return;
    const el = listRef.current?.querySelector<HTMLElement>(
      `.chapter-catalog-item.active, [data-chapter-id="${currentChapterId}"]`,
    );
    el?.scrollIntoView({ block: "center", inline: "nearest" });
  }, [open, activeRange, currentChapterId, query]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const searching = query.trim().length > 0;
  const searchHits = searching ? filterChaptersByTitle(chapters, query) : [];
  const visible = searching
    ? searchHits
    : chaptersInRange(chapters, activeRange || ranges[0] || null);

  const jumpByOrdinal = () => {
    const result = resolveOrdinalJump(chapters, ordinalInput);
    if (!result.ok) {
      setOrdinalError(
        result.reason === "out_of_range"
          ? `本书共${result.total}章`
          : "请输入有效章节序号",
      );
      return;
    }
    setOrdinalError(null);
    onSelectChapter(result.chapter.id);
  };

  return (
    <div
      className="chapter-catalog-drawer"
      data-testid="chapter-catalog-drawer"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="chapter-catalog-panel chapter-navigator-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="chapter-catalog-title"
      >
        <div className="chapter-catalog-head">
          <h3 id="chapter-catalog-title">章节目录</h3>
          <button
            type="button"
            className="chapter-catalog-close"
            aria-label="关闭"
            data-testid="chapter-catalog-close"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <div className="chapter-catalog-context">
          <strong className="chapter-catalog-book" title={bookTitle}>
            {bookTitle}
          </strong>
          <span className="chapter-catalog-count" data-testid="chapter-navigator-count">
            {total > 0 ? `共 ${total} 章` : "尚未识别到章节"}
          </span>
        </div>

        <div className="chapter-navigator-controls" data-testid="chapter-navigator-controls">
          <label className="chapter-navigator-field">
            <span className="sr-only">搜索章节标题</span>
            <input
              ref={searchRef}
              type="search"
              value={query}
              placeholder="搜索章节标题"
              data-testid="chapter-navigator-search"
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="chapter-navigator-jump">
            <label className="chapter-navigator-field chapter-navigator-ordinal">
              <span className="sr-only">章节序号</span>
              <input
                type="text"
                inputMode="numeric"
                value={ordinalInput}
                placeholder="序号"
                data-testid="chapter-navigator-ordinal"
                aria-invalid={Boolean(ordinalError)}
                onChange={(e) => {
                  setOrdinalInput(e.target.value);
                  setOrdinalError(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    jumpByOrdinal();
                  }
                }}
              />
            </label>
            <button
              type="button"
              className="primary"
              data-testid="chapter-navigator-jump"
              onClick={jumpByOrdinal}
            >
              跳转
            </button>
          </div>
          {ordinalError ? (
            <p className="chapter-navigator-error" data-testid="chapter-navigator-ordinal-error">
              {ordinalError}
            </p>
          ) : null}
        </div>

        {!searching && ranges.length > 1 ? (
          <div
            className="chapter-navigator-ranges"
            data-testid="chapter-navigator-ranges"
            role="listbox"
            aria-label="章节区间"
          >
            {ranges.map((range) => {
              const selected =
                activeRange?.startOrdinal === range.startOrdinal &&
                activeRange?.endOrdinal === range.endOrdinal;
              return (
                <button
                  key={range.label}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  className={`chapter-navigator-range${selected ? " selected" : ""}`}
                  data-testid={`chapter-range-${range.startOrdinal}-${range.endOrdinal}`}
                  onClick={() => setActiveRange(range)}
                >
                  {range.label}
                </button>
              );
            })}
          </div>
        ) : null}

        <div className="chapter-catalog-list chapter-navigator-list" ref={listRef}>
          {!total ? (
            <p className="chapter-navigator-empty" data-testid="chapter-navigator-empty">
              尚未识别到章节
            </p>
          ) : searching && !visible.length ? (
            <p className="chapter-navigator-empty" data-testid="chapter-navigator-no-results">
              没有找到匹配章节
            </p>
          ) : (
            visible.map((c) => {
              const ordinal = bodyOrdinalOf(chapters, c.id);
              const title = c.display_title || c.title;
              return (
                <button
                  key={c.id}
                  type="button"
                  className={`chapter-catalog-item${c.id === currentChapterId ? " active" : ""}`}
                  data-testid={`catalog-chapter-${c.id}`}
                  data-chapter-id={c.id}
                  title={title}
                  onClick={() => onSelectChapter(c.id)}
                >
                  <span className="chapter-catalog-item-num">
                    {chapterListLabel(c, ordinal)}
                  </span>
                  <span className="chapter-catalog-item-title">{title}</span>
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
