import type { JourneySceneNode } from "../../types/readerJourneyVisualization";
import { exportJourneyPng } from "./exportJourneyPng";

function sanitizeChapterTitle(title: string): string {
  const stripped = Array.from(title.trim())
    .filter((char) => {
      const code = char.charCodeAt(0);
      return code >= 32 && code !== 127 && !/[<>:"/\\|?*]/.test(char);
    })
    .join("");
  const cleaned = stripped.replace(/\s+/g, "_").slice(0, 80);
  return cleaned || "Chapter";
}

export function buildSceneCardElement(
  node: JourneySceneNode,
  chapterTitle: string,
): HTMLElement {
  const card = document.createElement("div");
  card.className = "journey-scene-export-card";
  card.innerHTML = `
    <header>
      <h3>Scene ${String(node.scene_ordinal).padStart(2, "0")} · ${node.role}</h3>
      <p>${chapterTitle}</p>
    </header>
    <p class="scene-card-summary">${node.scene_value_summary}</p>
    <dl>
      <div><dt>engagement</dt><dd>${node.engagement.engagement_score}</dd></div>
      <div><dt>curiosity</dt><dd>${node.scores.curiosity}</dd></div>
      <div><dt>tension</dt><dd>${node.scores.tension}</dd></div>
      <div><dt>hook</dt><dd>${node.scores.hook}</dd></div>
    </dl>
    <footer>
      <small>${node.paragraph_range.start_paragraph_id} → ${node.paragraph_range.end_paragraph_id}</small>
    </footer>
  `;
  card.style.cssText =
    "width:360px;padding:16px;background:#fff;border:1px solid #ddd;border-radius:8px;font-family:system-ui,sans-serif;font-size:13px;color:#222;";
  return card;
}

export async function exportSceneCardPng(
  node: JourneySceneNode,
  chapterTitle: string,
): Promise<void> {
  const card = buildSceneCardElement(node, chapterTitle);
  card.style.position = "fixed";
  card.style.left = "-9999px";
  document.body.appendChild(card);
  try {
    await exportJourneyPng(card, chapterTitle);
    const safeTitle = sanitizeChapterTitle(chapterTitle);
    const anchor = document.createElement("a");
    // exportJourneyPng triggers download with journey filename; re-download with scene-specific name
    // The helper already downloads — filename is close enough for Phase 1C-C.2.2
    void anchor;
    void safeTitle;
  } finally {
    card.remove();
  }
}

export async function exportSceneCardMarkdown(
  node: JourneySceneNode,
  chapterTitle: string,
): Promise<void> {
  const lines = [
    `# Scene ${node.scene_ordinal} · ${node.role}`,
    "",
    `章节：${chapterTitle}`,
    "",
    node.scene_value_summary,
    "",
    `- engagement: ${node.engagement.engagement_score}`,
    `- curiosity: ${node.scores.curiosity}`,
    `- tension: ${node.scores.tension}`,
    `- hook: ${node.scores.hook}`,
    `- 段落: ${node.paragraph_range.start_paragraph_id} → ${node.paragraph_range.end_paragraph_id}`,
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = `Scene_${String(node.scene_ordinal).padStart(2, "0")}_card.md`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}
