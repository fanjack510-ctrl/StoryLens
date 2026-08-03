/**
 * CHG-047 — ChapterFunctionsFreeModule restore + evidence bindings on product page.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChapterFunctionsFreeModule } from "../components/wholeBookFree/chapterFunctions/ChapterFunctionsFreeModule";
import * as freeApiMod from "../services/wholeBookFreeProductApi";

const getChapterFunctionsSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "getChapterFunctions");
const getChapterFunctionChapterSpy = vi.spyOn(
  freeApiMod.wholeBookFreeProductApi,
  "getChapterFunctionChapter",
);

const CF_PAGE = {
  result_status: "completed",
  contract_version: "v2",
  schema_version: "2.0.0",
  coverage_scope: "full_selected_range",
  chapter_functions: {
    contract_version: "v2",
    evidence_contract_version: "v2",
    coverage_scope: "full_selected_range",
    analysis_confidence: 0.84,
    limitations: [],
    context_capabilities: { structure_context_status: "available", structure_context_used: true },
    chapters: [],
  },
  items: [
    {
      chapter_id: 12,
      chapter_order: 2,
      chapter_title: "高潮章",
      primary_function: "climax",
      secondary_functions: [],
      observed_summary: {
        value: "决断。",
        status: "observed" as const,
        citation_ids: ["CIT-TEST0001-0001"],
        confidence: 0.8,
      },
      confidence: 0.8,
      supporting_citation_ids: ["CIT-TEST0001-0001"],
      limitations: [],
    },
  ],
  citation_evidence_bindings: [{ citation_id: "CIT-TEST0001-0001", evidence_id: 501 }],
  next_cursor: null,
  total_chapters: 1,
};

function renderModule(search = "?module=chapter_functions") {
  const onOpenEvidence = vi.fn();
  render(
    <MemoryRouter initialEntries={[`/books/1/whole-book${search}`]}>
      <Routes>
        <Route
          path="/books/:bookId/whole-book"
          element={
            <ChapterFunctionsFreeModule
              runId={42}
              runStatus="completed"
              pageMode="completed"
              onOpenEvidence={onOpenEvidence}
            />
          }
        />
      </Routes>
    </MemoryRouter>,
  );
  return onOpenEvidence;
}

describe("ChapterFunctionsFreeModule product restore", () => {
  afterEach(() => {
    cleanup();
    getChapterFunctionsSpy.mockReset();
    getChapterFunctionChapterSpy.mockReset();
  });

  it("enables evidence when citation bindings are present", async () => {
    getChapterFunctionsSpy.mockResolvedValue(CF_PAGE as never);
    getChapterFunctionChapterSpy.mockResolvedValue(CF_PAGE as never);
    const onOpenEvidence = renderModule();
    await screen.findByTestId("whole-book-free-chapter-functions-row-12");
    const btn = screen.getByTestId("whole-book-free-chapter-functions-evidence-12");
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    expect(onOpenEvidence).toHaveBeenCalledWith(501);
  });

  it("restores function filter, cursor intent, and chapter detail from URL", async () => {
    getChapterFunctionsSpy.mockResolvedValue(CF_PAGE as never);
    getChapterFunctionChapterSpy.mockResolvedValue(CF_PAGE as never);
    renderModule(
      "?module=chapter_functions&restoreFunction=climax&restoreChapter=12&cfFunction=climax&cfChapter=12",
    );
    await waitFor(() => {
      expect(screen.getByTestId("whole-book-free-chapter-functions-filter-function")).toHaveValue(
        "climax",
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("whole-book-free-chapter-functions-detail")).toHaveAttribute(
        "data-chapter-id",
        "12",
      );
    });
  });
});
