import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import {
  exportJourneyPng,
  JourneyExportError,
  JOURNEY_EXPORT_USER_MESSAGES,
} from "./exportJourneyPng";
import { openExportMenu, getJourneyExportButton } from "./journeyTestHelpers";

vi.mock("./exportJourneyPng", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./exportJourneyPng")>();
  return {
    ...actual,
    exportJourneyPng: vi.fn().mockResolvedValue({
      filename: "StoryLens_第一章_旅程分析_v1.1.png",
    }),
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.mocked(exportJourneyPng).mockResolvedValue({
    filename: "StoryLens_第一章_旅程分析_v1.1.png",
  });
});

const css = readFileSync(resolve(__dirname, "./readerJourney.css"), "utf8");
const visualization = buildMockReaderJourneyVisualization();

function renderWorkspace(initial = "/?overview=curve&scene=12") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <ReaderJourneyWorkspace
        visualization={visualization}
        chapterTitle="第一章"
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={12}
        activePhaseOrdinal={4}
      />
    </MemoryRouter>,
  );
}

function boxesOverlap(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
) {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

function mockBox(el: Element, box: { x: number; y: number; width: number; height: number }) {
  Object.defineProperty(el, "getBoundingClientRect", {
    configurable: true,
    value: () => ({
      x: box.x,
      y: box.y,
      width: box.width,
      height: box.height,
      top: box.y,
      left: box.x,
      right: box.x + box.width,
      bottom: box.y + box.height,
      toJSON: () => box,
    }),
  });
}


describe("Phase 1C-C.2.5.1 blocking UI fix", () => {
  it("uses analysis header instead of legacy overview mode tabs", () => {
    renderWorkspace();
    expect(screen.queryByTestId("journey-overview-mode-tabs")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-analysis-header")).toBeInTheDocument();
    expect(screen.getByTestId("journey-main-pane")).toContainElement(
      screen.getByTestId("journey-analysis-header"),
    );
    expect(screen.getByTestId("journey-overview-pane")).toContainElement(
      screen.getByTestId("journey-overview-curve"),
    );
  });

  it("removes compact/full marker toggle from ordinary chrome", () => {
    renderWorkspace();
    expect(screen.queryByTestId("journey-marker-toggle")).not.toBeInTheDocument();
    expect(css).not.toMatch(
      /\.journey-marker-toggle\s*\{[^}]*position:\s*absolute/s,
    );
    const main = screen.getByTestId("journey-main-pane");
    const children = Array.from(main.children).map((node) =>
      (node as HTMLElement).getAttribute("data-testid"),
    );
    expect(children.indexOf("journey-analysis-header")).toBeLessThan(
      children.indexOf("journey-export-root"),
    );
  });

  it("drops summary cards strip after hierarchy simplification", () => {
    renderWorkspace();
    expect(screen.queryByTestId("journey-summary-cards")).not.toBeInTheDocument();
    expect(css).toMatch(
      /\.journey-summary-strip,\s*\n?\s*\.journey-metric-strip,\s*\n?\s*\.journey-insight-strip\s*\{[^}]*grid-template-columns:/s,
    );
  });

  it("supports metric toolbar control without absolute stack", () => {
    renderWorkspace();
    const switcher = screen.getByTestId("journey-metric-switcher");
    expect(screen.getByTestId("journey-curve-toolbar")).toContainElement(switcher);
    expect(window.getComputedStyle(switcher).position).not.toBe("absolute");
  });

  it("keeps chart shell after phase nav in document flow", () => {
    renderWorkspace();
    const curve = screen.getByTestId("journey-overview-curve");
    const order = Array.from(curve.children).map((node) => {
      const el = node as HTMLElement;
      return el.getAttribute("data-testid") || el.className;
    });
    expect(order.indexOf("journey-phase-strip-wrap")).toBeLessThan(
      order.indexOf("journey-chart-shell"),
    );
    expect(css).toMatch(/\.journey-overview-curve \.journey-curve-section[\s\S]*min-height:\s*420px/);
  });

  it("has no overlapping chrome boxes at 1280px layout mock", () => {
    renderWorkspace();
    const header = screen.getByTestId("journey-analysis-header");
    const shell = screen.getByTestId("journey-chart-shell");
    const chart = screen.getByTestId("journey-curve-section");
    mockBox(header, { x: 0, y: 0, width: 900, height: 48 });
    mockBox(shell, { x: 0, y: 56, width: 900, height: 440 });
    mockBox(chart, { x: 56, y: 60, width: 844, height: 420 });
    const boxes = [header, shell].map((el) => el.getBoundingClientRect());
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        expect(boxesOverlap(boxes[i]!, boxes[j]!)).toBe(false);
      }
    }
  });

  it("has no overlapping chrome boxes at 1024px layout mock", () => {
    renderWorkspace();
    const header = screen.getByTestId("journey-analysis-header");
    const shell = screen.getByTestId("journey-chart-shell");
    const chart = screen.getByTestId("journey-curve-section");
    mockBox(header, { x: 0, y: 0, width: 700, height: 48 });
    mockBox(shell, { x: 0, y: 56, width: 700, height: 440 });
    mockBox(chart, { x: 56, y: 60, width: 644, height: 420 });
    const boxes = [header, shell].map((el) => el.getBoundingClientRect());
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        expect(boxesOverlap(boxes[i]!, boxes[j]!)).toBe(false);
      }
    }
  });

  it("binds export button to handler and shows exporting state", async () => {
    let resolveExport!: (value: { filename: string }) => void;
    vi.mocked(exportJourneyPng).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveExport = resolve;
        }),
    );
    renderWorkspace();
    const button = getJourneyExportButton();
    expect(button).toHaveAttribute("type", "button");
    fireEvent.click(button);
    expect(getJourneyExportButton()).toBeDisabled();
    await vi.waitFor(() => {
      expect(exportJourneyPng).toHaveBeenCalledTimes(1);
    });
    fireEvent.click(getJourneyExportButton());
    expect(exportJourneyPng).toHaveBeenCalledTimes(1);
    resolveExport({ filename: "StoryLens_第一章_完整旅程_v4.0.png" });
    expect(await screen.findByTestId("journey-export-feedback")).toHaveTextContent("已导出");
  });

  it("shows error when export reports missing root", async () => {
    vi.mocked(exportJourneyPng).mockRejectedValue(new JourneyExportError("root_missing"));
    renderWorkspace();
    fireEvent.click(openExportMenu());
    expect(await screen.findByTestId("journey-export-feedback")).toHaveTextContent(
      JOURNEY_EXPORT_USER_MESSAGES.root_missing,
    );
    await vi.waitFor(() => expect(getJourneyExportButton()).not.toBeDisabled());
  });

  it("shows error when chart is not rendered", async () => {
    vi.mocked(exportJourneyPng).mockRejectedValue(new JourneyExportError("not_rendered"));
    renderWorkspace();
    fireEvent.click(openExportMenu());
    expect(await screen.findByTestId("journey-export-feedback")).toHaveTextContent(
      JOURNEY_EXPORT_USER_MESSAGES.not_rendered,
    );
  });

  it("exports from legacy overview=questions while staying on journey analysis", async () => {
    renderWorkspace("/?overview=questions&scene=12");
    expect(screen.getByTestId("journey-overview-curve")).toBeInTheDocument();
    fireEvent.click(openExportMenu());
    await vi.waitFor(() => {
      expect(exportJourneyPng).toHaveBeenCalled();
    });
    expect(screen.getByTestId("journey-overview-curve")).toBeInTheDocument();
    expect(screen.getByTestId("journey-export-root")).toHaveAttribute(
      "data-overview-mode",
      "curve",
    );
  });

  it("waits for render then calls exportJourneyPng with export root", async () => {
    renderWorkspace("/?overview=diagnosis&scene=12");
    fireEvent.click(openExportMenu());
    await vi.waitFor(() => {
      expect(exportJourneyPng).toHaveBeenCalled();
    });
    const [root] = vi.mocked(exportJourneyPng).mock.calls[0]!;
    expect(root).toBeInstanceOf(HTMLElement);
    expect((root as HTMLElement).getAttribute("data-reader-journey-export-root")).toBe(
      "true",
    );
  });

  it("shows success feedback with filename", async () => {
    renderWorkspace();
    fireEvent.click(openExportMenu());
    const feedback = await screen.findByTestId("journey-export-feedback");
    expect(feedback).toHaveTextContent(/已导出.*StoryLens_第一章/);
    expect(feedback).toHaveAttribute("data-status", "succeeded");
  });

  it("shows failure feedback and restores button", async () => {
    vi.mocked(exportJourneyPng).mockRejectedValue(new JourneyExportError("image_failed"));
    renderWorkspace();
    fireEvent.click(openExportMenu());
    const feedback = await screen.findByTestId("journey-export-feedback");
    expect(feedback).toHaveTextContent(JOURNEY_EXPORT_USER_MESSAGES.image_failed);
    expect(feedback).toHaveAttribute("data-status", "failed");
    await vi.waitFor(() => expect(getJourneyExportButton()).not.toBeDisabled());
    expect(getJourneyExportButton()).toHaveTextContent("导出 PNG");
  });

  it("keeps scene and lens after export from legacy questions URL", async () => {
    renderWorkspace("/?overview=questions&scene=12");
    fireEvent.click(screen.getByTestId("journey-lens-reading_tension"));
    fireEvent.click(openExportMenu());
    await vi.waitFor(() => expect(exportJourneyPng).toHaveBeenCalled());
    expect(screen.getByTestId("journey-overview-curve")).toBeInTheDocument();
    expect(screen.getByTestId("journey-lens-reading_tension")).toHaveAttribute("aria-current", "true");
    expect(screen.getByTestId("scene-detail-title")).toHaveTextContent(/场景12/);
  });

  it("keeps journey analysis after export from legacy diagnosis URL", async () => {
    renderWorkspace("/?overview=diagnosis&scene=12");
    fireEvent.click(openExportMenu());
    await vi.waitFor(() => expect(exportJourneyPng).toHaveBeenCalled());
    expect(screen.getByTestId("journey-overview-curve")).toBeInTheDocument();
    expect(screen.getByTestId("journey-export-root")).toHaveAttribute(
      "data-overview-mode",
      "curve",
    );
  });

  it("does not invoke analysis APIs during export UI flow", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    renderWorkspace();
    fireEvent.click(openExportMenu());
    await vi.waitFor(() => expect(exportJourneyPng).toHaveBeenCalled());
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});

describe("Phase 1C-C.2.5.1 exportJourneyPng helpers", () => {
  afterEach(() => {
    document.body.querySelectorAll("[data-reader-journey-export-root]").forEach((node) => {
      if (!node.closest("[data-testid='journey-workspace']")) node.remove();
    });
  });

  it("clicks a download anchor with the expected filename", async () => {
    const { exportJourneyPng: realExport } =
      await vi.importActual<typeof import("./exportJourneyPng")>("./exportJourneyPng");

    const root = document.createElement("div");
    root.setAttribute("data-reader-journey-export-root", "true");
    root.setAttribute("data-testid", "journey-export-root-helper");
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("data-testid", "journey-curve-svg");
    svg.setAttribute("width", "520");
    svg.setAttribute("height", "260");
    root.appendChild(svg);
    document.body.appendChild(root);
    mockBox(root, { x: 0, y: 0, width: 520, height: 260 });
    mockBox(svg, { x: 0, y: 0, width: 520, height: 260 });

    const clicks: string[] = [];
    const objectUrls: string[] = [];
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: (blob: Blob) => {
        const href = `blob:test-${objectUrls.length}`;
        objectUrls.push(href);
        void blob;
        return href;
      },
      revokeObjectURL: vi.fn(),
    });

    const originalCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = originalCreate(tag);
      if (tag === "a") {
        const anchor = el as HTMLAnchorElement;
        anchor.click = () => {
          clicks.push(anchor.download);
        };
      }
      if (tag === "canvas") {
        const canvas = el as HTMLCanvasElement;
        canvas.getContext = ((() =>
          ({
            fillStyle: "",
            fillRect: () => undefined,
            drawImage: () => undefined,
            scale: () => undefined,
            font: "",
            fillText: () => undefined,
          })) as unknown) as HTMLCanvasElement["getContext"];
        canvas.toBlob = (cb) => {
          cb?.(new Blob(["png"], { type: "image/png" }));
        };
      }
      return el;
    });

    class FakeImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      crossOrigin = "";
      set src(_value: string) {
        queueMicrotask(() => this.onload?.());
      }
    }
    vi.stubGlobal("Image", FakeImage);

    try {
      const result = await realExport(root, "第一章");
      expect(result.filename).toBe("StoryLens_第一章_完整旅程_v4.0.png");
      expect(clicks).toContain("StoryLens_第一章_完整旅程_v4.0.png");
    } finally {
      root.remove();
      vi.unstubAllGlobals();
      vi.restoreAllMocks();
    }
  });

  it("throws not_rendered when journey export root has no chart svg", async () => {
    const { exportJourneyPng: realExport, JourneyExportError: Err } =
      await vi.importActual<typeof import("./exportJourneyPng")>("./exportJourneyPng");
    const empty = document.createElement("div");
    empty.setAttribute("data-reader-journey-export-root", "true");
    empty.setAttribute("data-testid", "journey-export-root-helper-empty");
    document.body.appendChild(empty);
    mockBox(empty, { x: 0, y: 0, width: 100, height: 80 });
    try {
      await expect(realExport(empty, "X")).rejects.toBeInstanceOf(Err);
      await expect(realExport(empty, "X")).rejects.toMatchObject({ code: "not_rendered" });
    } finally {
      empty.remove();
    }
  });
});

describe("Phase 1C-C.2.5.1 DOM contract", () => {
  it("exposes stable export root attribute", () => {
    renderWorkspace();
    const roots = screen.getAllByTestId("journey-export-root");
    expect(roots).toHaveLength(1);
    expect(roots[0]).toHaveAttribute("data-reader-journey-export-root", "true");
    expect(within(roots[0]!).getByTestId("journey-export-title")).toBeInTheDocument();
  });
});
