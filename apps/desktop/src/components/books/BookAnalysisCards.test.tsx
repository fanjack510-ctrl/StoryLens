import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { BookAnalysisCards } from "./BookAnalysisCards";

const chapterAction = {
  label: "分析本章",
  disabled: false,
  onClick: vi.fn(),
};

function renderCards(
  overrides: Partial<ComponentProps<typeof BookAnalysisCards>> = {},
) {
  return render(
    <MemoryRouter>
      <BookAnalysisCards
        bookId={18}
        isReference={false}
        isShortForm={false}
        chapterAction={chapterAction}
        profileUnconfirmed={false}
        profileHref="/books/18/profile?from=chapter&chapterId=47838"
        chapterTitle="第一章｜风雨来临"
        chapterCount={564}
        {...overrides}
      />
    </MemoryRouter>,
  );
}

describe("BookAnalysisCards analysis decision flow", () => {
  it("does not expose analysis choices while profile status is loading", () => {
    renderCards({ profilePending: true });

    expect(screen.getByTestId("book-analysis-profile-loading")).toHaveTextContent(
      "正在确认作品画像状态",
    );
    expect(screen.queryByTestId("book-analysis-scope-choice")).not.toBeInTheDocument();
  });

  it("shows only the profile step before the profile is confirmed", () => {
    renderCards({ profileUnconfirmed: true });

    expect(screen.getByTestId("book-analysis-profile-gate")).toHaveTextContent(
      "先确认这本书该按什么标准分析",
    );
    expect(screen.getByTestId("book-analysis-go-profile")).toHaveAttribute(
      "href",
      "/books/18/profile?from=chapter&chapterId=47838",
    );
    expect(screen.queryByTestId("ba-card-chapter")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ba-go-whole-book")).not.toBeInTheDocument();
  });

  it("shows chapter and whole-book analysis as equal scope choices after confirmation", () => {
    const onChapter = vi.fn();
    renderCards({ chapterAction: { ...chapterAction, onClick: onChapter } });

    const choices = screen.getByTestId("book-analysis-scope-choice");
    expect(choices).toContainElement(screen.getByTestId("ba-card-chapter"));
    expect(choices).toContainElement(screen.getByTestId("book-analysis-whole-entry"));
    expect(screen.getByTestId("ba-card-chapter")).toHaveTextContent("第一章｜风雨来临");
    expect(screen.getByTestId("book-analysis-whole-entry")).toHaveTextContent("564 章");
    expect(screen.getByTestId("ba-go-whole-book")).toHaveAttribute(
      "href",
      "/books/18/whole-book",
    );

    fireEvent.click(screen.getByRole("button", { name: "分析本章" }));
    expect(onChapter).toHaveBeenCalledTimes(1);
  });
});
