import { describe, expect, it } from "vitest";
import { scrollReadingPaneToTop } from "./chapterNavigation";

describe("scrollReadingPaneToTop", () => {
  it("resets reading-content-scroll-region scrollTop", () => {
    document.body.innerHTML = `
      <div data-testid="reading-content-scroll-region" class="reading-content-scroll-region">
        <div style="height:800px"></div>
      </div>
      <div class="workspace-reader">
        <div style="height:800px"></div>
      </div>
    `;
    const region = document.querySelector(
      '[data-testid="reading-content-scroll-region"]',
    ) as HTMLElement;
    const reader = document.querySelector(".workspace-reader") as HTMLElement;
    region.scrollTop = 120;
    reader.scrollTop = 90;
    scrollReadingPaneToTop();
    expect(region.scrollTop).toBe(0);
    expect(reader.scrollTop).toBe(90);
  });
});
