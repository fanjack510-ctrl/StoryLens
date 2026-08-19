import { describe, expect, it } from "vitest";
import { buildShortFormHtml, shortFormFileName } from "./shortFormExport";
import type { ShortFormReading } from "../../services/shortFormApi";

/** The sheet is a worksheet, not a report — it is read beside the text, so nothing in it may
 *  be truncated. These pin that, and the charset, which is the difference between a printable
 *  sheet and six pages of mojibake. */

function reading(segments: number): ShortFormReading {
  return {
    id: 1,
    genre: "言情",
    provider_name: "deepseek",
    model_name: "deepseek-v4-flash",
    segments_planned: segments,
    segments_resplit: 2,
    provider_calls: 9,
    created_at: "2026-08-19 01:00:00",
    result: {
      version: "1.0",
      availability: "available",
      title: "老屋",
      character_count: 27_766,
      one_line: "她为还清母亲欠下的债，把老屋改成早点铺",
      genre: "言情",
      beats: [
        { beat: "起", segment_start: 1, segment_end: 4, title: "债主上门", summary: "开局" },
        { beat: "承", segment_start: 5, segment_end: 12, title: "支起早点铺", summary: "过程" },
        { beat: "转", segment_start: 13, segment_end: 22, title: "存折是假的", summary: "转折" },
        { beat: "合", segment_start: 23, segment_end: segments, title: "赎回", summary: "收束" },
      ],
      segments: Array.from({ length: segments }, (_, i) => ({
        index: i + 1,
        paragraph_start: i * 10 + 1,
        paragraph_end: i * 10 + 10,
        characters: 800,
        phase: "陷入危机",
        setting: "老屋/女主、债主",
        beats: ["债主上门", "她翻出母亲的存折"],
        craft: i % 5 === 0 ? "" : "把坏消息放在她刚以为熬过去的时候。",
        emotion_note: "至暗时刻",
        emotion_direction: (["up", "down", "flat"] as const)[i % 3],
        callback: i === 3 ? "呼应第 1 段的老规矩" : "",
        evidence: [],
      })),
      recurring: [{ phrase: "老规矩", segments: [1, 3] }],
      emotion_up: ["第 4 段：第一天卖光了"],
      emotion_down: ["第 1 段：债主上门"],
    },
  };
}

describe("shortFormExport", () => {
  it("prints every scene, however many there are", () => {
    // No page budget, unlike the whole-book report. That one is an argument and is capped at
    // twenty pages because nobody finishes a report that grows with the book; this is read
    // beside the text, and dropping rows would defeat its only purpose.
    for (const count of [8, 34, 70]) {
      const html = buildShortFormHtml(reading(count));
      expect((html.match(/<tr class="dir-/g) ?? []).length).toBe(count);
    }
  });

  it("declares its charset", () => {
    // Opened as file:/// by a headless Chromium. Without this a Chinese Windows decodes it with
    // the system codepage and the whole sheet prints as mojibake.
    const html = buildShortFormHtml(reading(4));
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain("<meta charset=");
  });

  it("leaves an empty craft note empty", () => {
    // The instruction tells the model to leave this blank when a segment has nothing to teach.
    // A manufactured 「这里写得不错」 would be worse than a gap, and so would a silent fill.
    const html = buildShortFormHtml(reading(6));
    expect(html).toContain('<td class="craft">—</td>');
  });

  it("names the file after the piece", () => {
    expect(shortFormFileName(reading(3))).toBe("老屋-短篇精读.html");
  });
});

describe("callback", () => {
  it("shows what a segment reaches back to, and shows nothing when it reaches back to nothing", () => {
    // Inside the craft cell rather than a seventh column: the corpus's template is six wide,
    // and a callback is a property of the craft note rather than a peer of it.
    const html = buildShortFormHtml(reading(6));
    expect(html).toContain("↩ 呼应第 1 段的老规矩");
    expect((html.match(/class="cb"/g) ?? []).length).toBe(1);
  });
});

describe("recurring", () => {
  it("prints the wordings that come back, and where", () => {
    // Labelled as comparison rather than judgement on the page and here, because that is what
    // it is: the engine compared the prose and these strings came back. Which of them are
    // motifs is the reader's call.
    const html = buildShortFormHtml(reading(6));
    expect(html).toContain("反复出现的说法");
    expect(html).toContain("老规矩");
    expect(html).toContain("第 1、3 段");
  });
});
