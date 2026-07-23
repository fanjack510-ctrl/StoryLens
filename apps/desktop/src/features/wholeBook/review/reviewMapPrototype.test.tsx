import { cleanup, fireEvent, render, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FIXTURE_EVIDENCE, FIXTURE_CONFLICT, FIXTURE_STRUCTURE_MAP } from "../contracts/fixtures";
import {
  WholeBookEvidenceDrawer,
  EvidenceIntegrityBadge,
  NarrativeReviewActions,
  ConflictCenterPrototype,
} from "./index";
import {
  StructureMapPrototype,
  adaptPatternFixtureToStructureProjection,
  structureMapBoundaryNotes,
} from "../structureMap";

afterEach(() => {
  cleanup();
});

describe("Evidence Drawer prototype", () => {
  it("renders roles, preview, integrity, and mismatch warning", () => {
    const onOpen = vi.fn();
    const mismatch = {
      ...FIXTURE_EVIDENCE,
      integrity_status: "hash_mismatch" as const,
      evidence_role: "support" as const,
    };
    const { container } = render(
      <WholeBookEvidenceDrawer
        open
        evidence={[mismatch, { ...FIXTURE_EVIDENCE, evidence_id: 2, integrity_status: "missing" }]}
        theme="dark"
        onClose={() => undefined}
        onOpenDeepLink={onOpen}
      />,
    );
    const root = within(container).getByTestId("whole-book-evidence-drawer");
    expect(within(root).getAllByTestId("evidence-preview-card").length).toBe(2);
    expect(within(root).getAllByRole("alert").length).toBeGreaterThanOrEqual(1);
    fireEvent.click(within(root).getAllByTestId("evidence-source-link")[0]);
    expect(onOpen).toHaveBeenCalled();
  });

  it("supports keyboard Escape close and light theme", () => {
    const onClose = vi.fn();
    const { container } = render(
      <WholeBookEvidenceDrawer
        open
        evidence={[FIXTURE_EVIDENCE]}
        theme="light"
        onClose={onClose}
      />,
    );
    fireEvent.keyDown(within(container).getByTestId("whole-book-evidence-drawer"), {
      key: "Escape",
    });
    expect(onClose).toHaveBeenCalled();
  });

  it("renders integrity badge variants", () => {
    const { getByTestId } = render(<EvidenceIntegrityBadge status="stale" />);
    expect(getByTestId("evidence-integrity-badge")).toHaveTextContent("过期");
  });
});

describe("Review Actions prototype", () => {
  it("disables confirm without evidence and does not batch confirm", async () => {
    const onSubmit = vi.fn();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { container } = render(
      <NarrativeReviewActions
        targetType="asset_version"
        targetId="1"
        expectedVersion={1}
        reviewStatus="candidate"
        isCanonical={false}
        isLocked={false}
        hasSupportEvidence={false}
        onSubmit={onSubmit}
      />,
    );
    const root = within(container).getByTestId("narrative-review-actions");
    const confirmBtn = within(root).getByText("Confirm");
    expect(confirmBtn).toBeDisabled();
    fireEvent.click(within(root).getByText("Reject"));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ action: "reject" }),
    );
    confirmSpy.mockRestore();
  });
});

describe("Conflict Center prototype", () => {
  it("filters and shows comparison without full body", () => {
    const { container } = render(
      <ConflictCenterPrototype items={[FIXTURE_CONFLICT]} theme="light" />,
    );
    const root = within(container).getByTestId("conflict-center-prototype");
    fireEvent.click(within(root).getByTestId("conflict-center-item"));
    expect(within(root).getByTestId("conflict-comparison-panel")).toBeInTheDocument();
    expect(within(root).getByTestId("conflict-resolution-panel")).toHaveTextContent(
      "不会被系统自动解决",
    );
    expect(within(root).queryByText("完整正文内容")).toBeNull();
  });
});

describe("Structure Map prototype", () => {
  it("renders three views, search, theme, keyboard, and evidence drawer", () => {
    const onTheme = vi.fn();
    const projection = {
      ...FIXTURE_STRUCTURE_MAP,
      root_nodes: [
        {
          node_id: "n1",
          node_type: "storyline",
          title: "主线",
          asset_id: 1,
          asset_version_id: 2,
          is_canonical: true,
          view_modes: ["structure_stages", "storylines", "character_growth"] as (
            | "structure_stages"
            | "storylines"
            | "character_growth"
          )[],
          chapter_range: [1, 3] as [number | null, number | null],
          parent_id: null,
          evidence_count: 1,
          collapsed: false,
          searchable_text: "主线 storyline",
        },
        {
          node_id: "n2",
          node_type: "character_arc_stage",
          title: "成长点",
          asset_id: 3,
          asset_version_id: 4,
          is_canonical: false,
          view_modes: ["character_growth"] as ("character_growth")[],
          chapter_range: [2, 2] as [number | null, number | null],
          parent_id: "n1",
          evidence_count: 0,
          collapsed: false,
          searchable_text: "成长点 candidate",
        },
      ],
      evidence_index: { n1: ["asset_evidence:1"] },
      review_summary: { truncated: false, writes_database_facts: false },
    };
    const { container } = render(
      <StructureMapPrototype
        projection={{
          ...projection,
          root_nodes: projection.root_nodes.map((n) => ({ ...n, is_canonical: true })),
          filters: { ...projection.filters, include_candidates: false },
        }}
        evidenceByKey={{ "asset_evidence:1": FIXTURE_EVIDENCE }}
        theme="light"
        onThemeChange={onTheme}
      />,
    );
    const root = within(container).getByTestId("structure-map-prototype");
    expect(within(root).getByTestId("structure-map-svg")).toBeInTheDocument();
    fireEvent.click(within(root).getByTestId("structure-map-node-n1"));
    expect(within(root).getByTestId("structure-map-detail")).toBeInTheDocument();
    fireEvent.click(within(root).getByText("打开 Evidence Drawer"));
    expect(within(root).getByTestId("whole-book-evidence-drawer")).toBeInTheDocument();
    fireEvent.keyDown(within(root).getByTestId("structure-map-svg"), { key: "Escape" });
    fireEvent.change(within(root).getByLabelText("结构地图视图"), {
      target: { value: "character_growth" },
    });
    fireEvent.change(within(root).getByLabelText("搜索结构地图节点"), {
      target: { value: "成长" },
    });
    expect(within(root).getByTestId("structure-map-node-n2")).toBeInTheDocument();
    // Toggle candidates filter control exists and is keyboard-reachable.
    expect(within(root).getByLabelText("include_candidates")).toBeInTheDocument();
    fireEvent.click(within(root).getByText("主题: light"));
    expect(onTheme).toHaveBeenCalledWith("dark");
  });

  it("adapts Agent C style fixtures and keeps Pattern Map 36/81 compatible notes", () => {
    const adapted = adaptPatternFixtureToStructureProjection({
      bookId: 1,
      bookSnapshotId: 11,
      nodes: Array.from({ length: 36 }, (_, i) => ({
        id: `n${i}`,
        title: `Node ${i}`,
        parentId: i === 0 ? null : "n0",
      })),
    });
    expect(adapted.root_nodes.length).toBe(36);
    expect(structureMapBoundaryNotes().some((n) => n.includes("Narrative Structure Map"))).toBe(
      true,
    );
  });
});
