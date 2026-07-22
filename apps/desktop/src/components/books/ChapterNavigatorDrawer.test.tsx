import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChapterNavigatorDrawer } from "./ChapterNavigatorDrawer";
import type { Chapter } from "../../types";

function makeChapters(count: number): Chapter[] {
  const rows: Chapter[] = [
    {
      id: 1,
      book_id: 3,
      chapter_index: 0,
      title: "资料",
      display_title: "资料",
      word_count: 1,
      section_type: "front_matter",
    },
  ];
  for (let i = 1; i <= count; i += 1) {
    rows.push({
      id: 1000 + i,
      book_id: 3,
      chapter_index: i,
      title: `第${i}章 标题${i}`,
      display_title: `第${i}章 标题${i}`,
      word_count: 10,
      section_type: "chapter",
      chapter_number_normalized: i,
    });
  }
  return rows;
}

afterEach(cleanup);

describe("ChapterNavigatorDrawer", () => {
  it("opens without changing route and supports ordinal jump", () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    const chapters = makeChapters(1299);
    render(
      <ChapterNavigatorDrawer
        open
        bookTitle="长篇测试"
        chapters={chapters}
        currentChapterId={1005}
        onClose={onClose}
        onSelectChapter={onSelect}
      />,
    );
    expect(screen.getByTestId("chapter-catalog-drawer")).toBeInTheDocument();
    expect(screen.getByTestId("chapter-navigator-count")).toHaveTextContent("共 1299 章");
    expect(screen.getByTestId("chapter-range-1-100")).toBeInTheDocument();
    expect(screen.getByTestId("chapter-range-1201-1299")).toBeInTheDocument();
    // Only current 100-chapter window is rendered (plus no front matter in body list).
    expect(screen.getByTestId("catalog-chapter-1005")).toBeInTheDocument();
    expect(screen.queryByTestId("catalog-chapter-1800")).not.toBeInTheDocument();

    fireEvent.change(screen.getByTestId("chapter-navigator-ordinal"), {
      target: { value: "800" },
    });
    fireEvent.click(screen.getByTestId("chapter-navigator-jump"));
    expect(onSelect).toHaveBeenCalledWith(1800);
  });

  it("shows range error and search empty state", () => {
    const chapters = makeChapters(12);
    render(
      <ChapterNavigatorDrawer
        open
        bookTitle="短篇"
        chapters={chapters}
        currentChapterId={1001}
        onClose={vi.fn()}
        onSelectChapter={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByTestId("chapter-navigator-ordinal"), {
      target: { value: "99" },
    });
    fireEvent.click(screen.getByTestId("chapter-navigator-jump"));
    expect(screen.getByTestId("chapter-navigator-ordinal-error")).toHaveTextContent(
      "本书共12章",
    );

    fireEvent.change(screen.getByTestId("chapter-navigator-search"), {
      target: { value: "不存在的关键词" },
    });
    expect(screen.getByTestId("chapter-navigator-no-results")).toHaveTextContent(
      "没有找到匹配章节",
    );
  });

  it("title search returns matching chapter", () => {
    const onSelect = vi.fn();
    const chapters = makeChapters(30);
    render(
      <ChapterNavigatorDrawer
        open
        bookTitle="书"
        chapters={chapters}
        currentChapterId={1001}
        onClose={vi.fn()}
        onSelectChapter={onSelect}
      />,
    );
    fireEvent.change(screen.getByTestId("chapter-navigator-search"), {
      target: { value: "标题12" },
    });
    const hit = screen.getByTestId("catalog-chapter-1012");
    expect(within(hit).getByText(/标题12/)).toBeInTheDocument();
    fireEvent.click(hit);
    expect(onSelect).toHaveBeenCalledWith(1012);
  });
});
