import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChapterListViewport } from "../components/books/ChapterListViewport";
import {
  scrollChapterListItemIntoViewIfNeeded,
} from "./chapterNavigation";
import type { Chapter } from "../types";

function ch(id: number, title: string): Chapter {
  return {
    id,
    book_id: 1,
    chapter_index: id,
    title,
    display_title: title,
    word_count: 10,
    section_type: "chapter",
    chapter_number_normalized: id,
  };
}

afterEach(() => cleanup());

describe("chapter list single-line rows", () => {
  it("renders fixed single-line chapter rows with ellipsis-friendly title", () => {
    render(
      <ChapterListViewport
        chapters={[
          ch(6, "第6章｜《陈氏编导法则》这是很长很长的标题"),
          ch(7, "第7章｜下一章"),
        ]}
        currentChapterId={6}
        onSelect={vi.fn()}
      />,
    );
    const selected = screen.getByTestId("workspace-chapter-item-selected");
    expect(selected).toHaveAttribute("data-row-kind", "chapter");
    expect(selected).toHaveAttribute("title", "第6章｜《陈氏编导法则》这是很长很长的标题");
    expect(selected.getAttribute("aria-label") || "").toContain("第6章｜《陈氏编导法则》");
    const title = selected.querySelector(".workspace-chapter-title") as HTMLElement;
    expect(title).toBeTruthy();
    const cs = getComputedStyle(title);
    // jsdom may not apply stylesheet; assert class contract used by CSS.
    expect(title.className).toContain("workspace-chapter-title");
    expect(selected.className).toContain("workspace-chapter-item");
    void cs;
  });
});

describe("scrollChapterListItemIntoViewIfNeeded", () => {
  it("does not scrollIntoView when item is fully visible", () => {
    document.body.innerHTML = `
      <div data-testid="chapter-list-scroll-region" style="height:200px;overflow:auto">
        <button class="workspace-chapter-item" data-chapter-id="2">2</button>
      </div>
    `;
    const root = document.querySelector(
      '[data-testid="chapter-list-scroll-region"]',
    ) as HTMLElement;
    const el = root.querySelector(".workspace-chapter-item") as HTMLElement;
    Object.defineProperty(root, "getBoundingClientRect", {
      value: () => ({ top: 0, bottom: 200, left: 0, right: 100, height: 200, width: 100 }),
    });
    Object.defineProperty(el, "getBoundingClientRect", {
      value: () => ({ top: 40, bottom: 76, left: 0, right: 100, height: 36, width: 100 }),
    });
    const spy = vi.fn();
    el.scrollIntoView = spy;
    expect(scrollChapterListItemIntoViewIfNeeded(root, 2)).toBe(false);
    expect(spy).not.toHaveBeenCalled();
  });

  it("scrolls with nearest when item is outside viewport", () => {
    document.body.innerHTML = `
      <div data-testid="chapter-list-scroll-region" style="height:200px;overflow:auto">
        <button class="workspace-chapter-item" data-chapter-id="9">9</button>
      </div>
    `;
    const root = document.querySelector(
      '[data-testid="chapter-list-scroll-region"]',
    ) as HTMLElement;
    const el = root.querySelector(".workspace-chapter-item") as HTMLElement;
    Object.defineProperty(root, "getBoundingClientRect", {
      value: () => ({ top: 0, bottom: 200, left: 0, right: 100, height: 200, width: 100 }),
    });
    Object.defineProperty(el, "getBoundingClientRect", {
      value: () => ({ top: 240, bottom: 276, left: 0, right: 100, height: 36, width: 100 }),
    });
    const spy = vi.fn();
    el.scrollIntoView = spy;
    expect(scrollChapterListItemIntoViewIfNeeded(root, 9)).toBe(true);
    expect(spy).toHaveBeenCalledWith({ block: "nearest", inline: "nearest" });
  });
});
