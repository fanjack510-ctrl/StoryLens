/**
 * Phase 1D-A: Single-Chapter Journey Template Governance tests.
 * Proves one canonical v2.7 template for all books/chapters/routes.
 * Zero model calls; no AnalysisRun / ReaderJourneyRun creation.
 */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneySyncWorkspace } from "./ReaderJourneySyncWorkspace";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import {
  buildSingleChapterTemplateFixtures,
  CANONICAL_TEMPLATE_ENTRY,
  extractJourneyTemplateSkeleton,
  skeletonSignature,
  type TemplateChapterFixture,
} from "./mockSingleChapterJourneyTemplateFixtures";
import { booksApi } from "../../services/booksApi";
import type { SceneResultItem } from "../../types";

vi.mock("./exportJourneyPng", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./exportJourneyPng")>();
  return {
    ...actual,
    exportJourneyPng: vi.fn().mockResolvedValue({
      filename: "StoryLens_Chapter_旅程分析_v1.1.png",
    }),
  };
});

vi.mock("../../services/booksApi", () => ({
  booksApi: {
    paragraphs: vi.fn(),
  },
}));

afterEach(cleanup);

beforeEach(() => {
  localStorage.clear();
});

const fixtures = buildSingleChapterTemplateFixtures();

/** Test-only stand-in marker — does not modify frozen v2.7 production files. */
function TemplateStandIn({
  marker,
  route,
  children,
}: {
  marker: string;
  route: "books" | "standalone" | "canonical";
  children: ReactNode;
}) {
  return (
    <div
      data-testid="template-stand-in"
      data-template-id="reader-journey-single-chapter"
      data-template-version="2.7"
      data-template-marker={marker}
      data-route-adapter={route}
    >
      {children}
    </div>
  );
}

function makeScenes(fixture: TemplateChapterFixture): SceneResultItem[] {
  return fixture.visualization.scene_nodes.map((node) => ({
    scene: {
      id: node.scene_id,
      scene_key: `S${node.scene_ordinal}`,
      ordinal: node.scene_ordinal,
      start_paragraph_id: node.paragraph_range.start_paragraph_id,
      end_paragraph_id: node.paragraph_range.end_paragraph_id,
      paragraph_count: node.paragraph_count,
      is_single_paragraph: false,
      boundary_source: "model_accepted",
      boundary_revision_id: 1,
      boundary_detected: true,
      boundary_confidence: 0.9,
    },
    analysis_artifact: null,
    evidence: [],
    illegal_evidence: [],
    revision: null,
  }));
}

function mockWorkspaceWidth(width = 1600) {
  Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
    configurable: true,
    value() {
      return {
        width,
        height: 900,
        top: 0,
        left: 0,
        bottom: 900,
        right: width,
        x: 0,
        y: 0,
        toJSON() {
          return {};
        },
      };
    },
  });
}

function renderCanonical(
  fixture: TemplateChapterFixture,
  options: {
    marker?: string;
    route?: "books" | "standalone" | "canonical";
    activeSceneOrdinal?: number | null;
    initial?: string;
  } = {},
) {
  mockWorkspaceWidth(1600);
  const marker = options.marker ?? "v2.7-base";
  const route = options.route ?? "canonical";
  return render(
    <MemoryRouter initialEntries={[options.initial ?? "/?tab=reader-journey&overview=curve"]}>
      <div style={{ width: 1600 }}>
        <TemplateStandIn marker={marker} route={route}>
          <ReaderJourneyWorkspace
            visualization={fixture.visualization}
            chapterTitle={fixture.chapterTitle}
            onLocateEvidence={vi.fn()}
            activeSceneOrdinal={options.activeSceneOrdinal ?? null}
            activePhaseOrdinal={null}
          />
        </TemplateStandIn>
      </div>
    </MemoryRouter>,
  );
}

function renderViaRouteAdapter(
  fixture: TemplateChapterFixture,
  route: "books" | "standalone",
  marker: string,
) {
  vi.mocked(booksApi.paragraphs).mockResolvedValue({
    items: fixture.visualization.scene_nodes.flatMap((node) =>
      node.evidence_paragraph_ids.map((id, index) => ({
        id,
        chapter_id: fixture.chapterId,
        paragraph_index: index + 1,
        raw_text: `段落 ${id}`,
      })),
    ),
    offset: 0,
    limit: 500,
    total: 10,
    has_more: false,
  });

  const initial =
    route === "books"
      ? `/books/${fixture.bookId}?chapter=${fixture.chapterId}&analysisRun=999&view=result&tab=reader-journey&mode=journey`
      : `/analysis-runs/999/results?tab=reader-journey&mode=journey`;

  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[initial]}>
        <TemplateStandIn marker={marker} route={route}>
          <ReaderJourneySyncWorkspace
            chapterId={fixture.chapterId}
            chapterTitle={fixture.chapterTitle}
            scenes={makeScenes(fixture)}
            visualization={fixture.visualization}
            tab="journey"
            onTabChange={vi.fn()}
          />
        </TemplateStandIn>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Phase 1D-A single-chapter journey template governance", () => {
  it("covers two books and four chapters in fixtures", () => {
    const bookIds = new Set(fixtures.map((f) => f.bookId));
    expect(bookIds.size).toBe(2);
    expect(fixtures).toHaveLength(4);
    expect(CANONICAL_TEMPLATE_ENTRY).toContain("ReaderJourneyWorkspace.tsx");
  });

  it("uses the same canonical entry for all books and chapters", () => {
    const signatures = fixtures.map((fixture) => {
      const { container, unmount } = renderCanonical(fixture);
      const skeleton = extractJourneyTemplateSkeleton(container);
      unmount();
      return skeletonSignature(skeleton);
    });
    expect(new Set(signatures).size).toBe(1);
  });

  it("keeps DOM skeleton when Scene counts differ", () => {
    const sceneCounts = fixtures.map((f) => f.visualization.scene_nodes.length);
    expect(new Set(sceneCounts).size).toBeGreaterThan(1);
    const signatures = fixtures.map((fixture) => {
      const { container, unmount } = renderCanonical(fixture);
      const sig = skeletonSignature(extractJourneyTemplateSkeleton(container));
      unmount();
      return sig;
    });
    expect(new Set(signatures).size).toBe(1);
  });

  it("keeps DOM skeleton when Phase counts differ", () => {
    const phaseCounts = fixtures.map((f) => f.visualization.phases.length);
    expect(new Set(phaseCounts).size).toBeGreaterThan(1);
    const signatures = fixtures.map((fixture) => {
      const { container, unmount } = renderCanonical(fixture);
      const sig = skeletonSignature(extractJourneyTemplateSkeleton(container));
      unmount();
      return sig;
    });
    expect(new Set(signatures).size).toBe(1);
  });

  it("keeps Inspector Shell for empty selection across fixtures", () => {
    for (const fixture of fixtures) {
      const { container, unmount } = renderCanonical(fixture, { activeSceneOrdinal: null });
      // Curve-first default keeps Inspector collapsed; open it without relying on toggle
      // (toggle would close an already-open pane left by local prefs / layout).
      const expand = container.querySelector('[data-testid="journey-inspector-summary-expand"]');
      if (expand) {
        fireEvent.click(expand);
      } else if (!container.querySelector('[data-testid="journey-detail-pane"]')) {
        const toggle = container.querySelector('[data-testid="journey-inspector-toggle"]');
        expect(toggle).toBeTruthy();
        fireEvent.click(toggle!);
      }
      expect(container.querySelector('[data-testid="journey-detail-pane"]')).toBeTruthy();
      expect(container.querySelector('[data-testid="journey-detail-empty"]')).toBeTruthy();
      unmount();
    }
  });

  it("keeps Books and Standalone journey DOM skeletons identical", () => {
    const a = fixtures[0];
    const b = fixtures[2];
    const books = renderViaRouteAdapter(a, "books", "v2.7-base");
    const booksSig = skeletonSignature(extractJourneyTemplateSkeleton(books.container));
    books.unmount();
    const standalone = renderViaRouteAdapter(b, "standalone", "v2.7-base");
    const standaloneSig = skeletonSignature(extractJourneyTemplateSkeleton(standalone.container));
    standalone.unmount();
    expect(booksSig).toBe(standaloneSig);
  });

  it("does not fork layout by bookId/chapterId (behavioral; static scan in checker)", () => {
    expect(fixtures[0].bookId).not.toBe(fixtures[2].bookId);
    expect(fixtures[0].chapterId).not.toBe(fixtures[1].chapterId);
    const signatures = [fixtures[0], fixtures[2]].map((fixture) => {
      const { container, unmount } = renderCanonical(fixture);
      const sig = skeletonSignature(extractJourneyTemplateSkeleton(container));
      unmount();
      return sig;
    });
    expect(signatures[0]).toBe(signatures[1]);
  });

  it("propagates a single test template marker to all chapters and both route adapters", () => {
    const before = "v2.7-base";
    const after = "v2.7-changed-stand-in";

    for (const fixture of fixtures) {
      const { container, unmount } = renderCanonical(fixture, { marker: before });
      expect(container.querySelector("[data-template-marker]")?.getAttribute("data-template-marker")).toBe(
        before,
      );
      unmount();
    }

    const booksMarkers: string[] = [];
    const standaloneMarkers: string[] = [];
    for (const fixture of fixtures) {
      const books = renderViaRouteAdapter(fixture, "books", after);
      booksMarkers.push(
        books.container.querySelector("[data-template-marker]")?.getAttribute("data-template-marker") || "",
      );
      expect(books.container.querySelector('[data-testid="journey-workspace"]')).toBeTruthy();
      books.unmount();

      const standalone = renderViaRouteAdapter(fixture, "standalone", after);
      standaloneMarkers.push(
        standalone.container
          .querySelector("[data-template-marker]")
          ?.getAttribute("data-template-marker") || "",
      );
      expect(standalone.container.querySelector('[data-testid="journey-workspace"]')).toBeTruthy();
      standalone.unmount();
    }

    expect(booksMarkers.every((m) => m === after)).toBe(true);
    expect(standaloneMarkers.every((m) => m === after)).toBe(true);
  });

  it("does not require re-running AnalysisRun or ReaderJourneyRun when template marker changes", () => {
    const fixture = fixtures[0];
    const vizBefore = fixture.visualization;
    const first = renderCanonical(fixture, { marker: "v2.7-base" });
    const textBefore = first.container.querySelector('[data-testid="journey-export-title"]')
      ?.textContent;
    first.unmount();

    const second = renderCanonical(fixture, { marker: "v2.7-changed-stand-in" });
    const textAfter = second.container.querySelector('[data-testid="journey-export-title"]')
      ?.textContent;
    const marker = second.container
      .querySelector("[data-template-marker]")
      ?.getAttribute("data-template-marker");
    second.unmount();

    expect(textBefore).toBe(textAfter);
    expect(marker).toBe("v2.7-changed-stand-in");
    expect(fixture.visualization).toBe(vizBefore);
    expect(fixture.visualization.visualization_version).toBe("1.1");
  });

  it("covers question/hook/evidence matrix without forking the template", () => {
    const withQ = fixtures.find((f) => f.tags.includes("has-questions"));
    const withoutQ = fixtures.find((f) => f.tags.includes("no-questions"));
    const withHook = fixtures.find((f) => f.tags.includes("has-hook-payoff"));
    const withoutHook = fixtures.find((f) => f.tags.includes("no-hook-payoff"));
    const sparse = fixtures.find((f) => f.tags.includes("evidence-sparse"));
    const rich = fixtures.find((f) => f.tags.includes("evidence-rich"));
    expect(withQ && withoutQ && withHook && withoutHook && sparse && rich).toBeTruthy();

    const subset = [withQ!, withoutQ!, withHook!, withoutHook!, sparse!, rich!];
    const signatures = subset.map((fixture) => {
      const { container, unmount } = renderCanonical(fixture, { activeSceneOrdinal: 1 });
      const sig = skeletonSignature(extractJourneyTemplateSkeleton(container));
      unmount();
      return sig;
    });
    expect(new Set(signatures).size).toBe(1);
    expect(sparse!.visualization.scene_nodes[0].evidence_count).toBeLessThanOrEqual(2);
    expect(rich!.visualization.scene_nodes[0].evidence_count).toBeGreaterThan(5);
  });

  it("records zero model / zero new-run intent for this suite", () => {
    // Governance phase invariant: these tests never invoke analysis APIs.
    expect(vi.isMockFunction(booksApi.paragraphs)).toBe(true);
  });
});
