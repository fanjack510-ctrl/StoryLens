/** Client-side partition edits mirroring backend scene_boundary_partition_ops (CHG-041). */

export type ScenePartition = {
  scene_order: number;
  start_paragraph_id: string;
  end_paragraph_id: string;
  included_in_journey: boolean;
};

function ordered(scenes: ScenePartition[]): ScenePartition[] {
  return [...scenes].sort((a, b) => a.scene_order - b.scene_order);
}

export function moveSceneBoundary(
  scenes: ScenePartition[],
  boundaryIndex: number,
  direction: "left" | "right",
  paragraphIds: string[],
): ScenePartition[] {
  const list = ordered(scenes).map((s) => ({ ...s }));
  if (boundaryIndex < 0 || boundaryIndex >= list.length - 1) {
    throw new Error("SCENE_PARTITION_ORDER_INVALID");
  }
  const left = list[boundaryIndex];
  const right = list[boundaryIndex + 1];
  const pos = Object.fromEntries(paragraphIds.map((id, index) => [id, index]));
  const leftStart = pos[left.start_paragraph_id];
  const leftEnd = pos[left.end_paragraph_id];
  const rightStart = pos[right.start_paragraph_id];
  if (leftEnd + 1 !== rightStart) throw new Error("SCENE_PARTITION_GAP");
  if (direction === "left") {
    if (leftStart >= leftEnd) throw new Error("SCENE_PARTITION_EMPTY_SCENE");
    const newEndIdx = leftEnd - 1;
    left.end_paragraph_id = paragraphIds[newEndIdx];
    right.start_paragraph_id = paragraphIds[newEndIdx + 1];
  } else {
    const rightEndPos = pos[right.end_paragraph_id];
    if (rightStart >= rightEndPos) throw new Error("SCENE_PARTITION_EMPTY_SCENE");
    const newStartIdx = rightStart + 1;
    right.start_paragraph_id = paragraphIds[newStartIdx];
    left.end_paragraph_id = paragraphIds[newStartIdx - 1];
  }
  return list;
}

export function addSceneBoundary(
  scenes: ScenePartition[],
  afterParagraphId: string,
  paragraphIds: string[],
): ScenePartition[] {
  const list = ordered(scenes).map((s) => ({ ...s }));
  const pos = Object.fromEntries(paragraphIds.map((id, index) => [id, index]));
  const splitIdx = pos[afterParagraphId];
  if (splitIdx == null || splitIdx >= paragraphIds.length - 1) {
    throw new Error("SCENE_SPLIT_INVALID_POSITION");
  }
  for (const scene of list.slice(0, -1)) {
    if (scene.end_paragraph_id === afterParagraphId) {
      throw new Error("SCENE_BOUNDARY_ALREADY_EXISTS");
    }
  }
  let targetIdx: number | null = null;
  for (let index = 0; index < list.length; index += 1) {
    const scene = list[index];
    const startI = pos[scene.start_paragraph_id];
    const endI = pos[scene.end_paragraph_id];
    if (startI <= splitIdx && splitIdx <= endI) {
      targetIdx = index;
      break;
    }
  }
  if (targetIdx == null) throw new Error("SCENE_SPLIT_INVALID_POSITION");
  const scene = list[targetIdx];
  const startI = pos[scene.start_paragraph_id];
  const endI = pos[scene.end_paragraph_id];
  if (splitIdx < startI || splitIdx >= endI) throw new Error("SCENE_SPLIT_INVALID_POSITION");
  if (startI === endI) throw new Error("SCENE_SPLIT_EMPTY_SCENE");
  const left: ScenePartition = {
    ...scene,
    end_paragraph_id: paragraphIds[splitIdx],
  };
  const right: ScenePartition = {
    scene_order: scene.scene_order + 1,
    start_paragraph_id: paragraphIds[splitIdx + 1],
    end_paragraph_id: scene.end_paragraph_id,
    included_in_journey: scene.included_in_journey,
  };
  const updated = [...list.slice(0, targetIdx), left, right, ...list.slice(targetIdx + 1)];
  return updated.map((item, index) => ({ ...item, scene_order: index + 1 }));
}

export function mergeSceneBoundary(
  scenes: ScenePartition[],
  boundaryIndex: number,
  paragraphIds: string[],
  includedInJourney?: boolean,
): ScenePartition[] {
  const list = ordered(scenes).map((s) => ({ ...s }));
  if (list.length <= 1) throw new Error("SCENE_PARTITION_EMPTY");
  if (boundaryIndex < 0 || boundaryIndex >= list.length - 1) {
    throw new Error("SCENE_PARTITION_ORDER_INVALID");
  }
  const pos = Object.fromEntries(paragraphIds.map((id, index) => [id, index]));
  const left = list[boundaryIndex];
  const right = list[boundaryIndex + 1];
  if (pos[left.end_paragraph_id] + 1 !== pos[right.start_paragraph_id]) {
    throw new Error("SCENE_PARTITION_GAP");
  }
  let mergedIncluded: boolean;
  if (includedInJourney != null) {
    mergedIncluded = includedInJourney;
  } else if (left.included_in_journey === right.included_in_journey) {
    mergedIncluded = left.included_in_journey;
  } else {
    throw new Error("SCENE_MERGE_INCLUDED_CONFLICT");
  }
  const merged: ScenePartition = {
    scene_order: left.scene_order,
    start_paragraph_id: left.start_paragraph_id,
    end_paragraph_id: right.end_paragraph_id,
    included_in_journey: mergedIncluded,
  };
  const updated = [...list.slice(0, boundaryIndex), merged, ...list.slice(boundaryIndex + 2)];
  return updated.map((item, index) => ({ ...item, scene_order: index + 1 }));
}

export function setSceneIncluded(
  scenes: ScenePartition[],
  sceneOrder: number,
  included: boolean,
): ScenePartition[] {
  const list = ordered(scenes).map((s) => ({ ...s }));
  const target = list.find((item) => item.scene_order === sceneOrder);
  if (!target) throw new Error("SCENE_PARTITION_ORDER_INVALID");
  target.included_in_journey = included;
  return list;
}

export type SceneBoundaryChangeSummary = {
  moved: number;
  added: number;
  merged: number;
  excluded: number;
};

export function computeSceneBoundaryChangeSummary(
  draft: ScenePartition[],
  model: ScenePartition[],
): SceneBoundaryChangeSummary {
  const summary: SceneBoundaryChangeSummary = { moved: 0, added: 0, merged: 0, excluded: 0 };
  const left = ordered(draft);
  const right = ordered(model);
  for (let index = 0; index < left.length; index += 1) {
    const l = left[index];
    const r = right[index];
    if (!r) {
      summary.added += 1;
      continue;
    }
    if (
      l.start_paragraph_id !== r.start_paragraph_id ||
      l.end_paragraph_id !== r.end_paragraph_id
    ) {
      summary.moved += 1;
    }
    if (l.included_in_journey !== r.included_in_journey && !l.included_in_journey) {
      summary.excluded += 1;
    }
  }
  if (right.length > left.length) {
    summary.merged += right.length - left.length;
  }
  return summary;
}

/** True when an add-split control should appear after this paragraph inside a scene. */
export function canSplitAfterParagraph(args: {
  paragraphId: string;
  sceneParagraphIds: string[];
  chapterParagraphIds: string[];
  boundaryAfterParagraphIds: Set<string>;
}): boolean {
  const { paragraphId, sceneParagraphIds, chapterParagraphIds, boundaryAfterParagraphIds } = args;
  if (sceneParagraphIds.length <= 1) return false;
  const lastInScene = sceneParagraphIds[sceneParagraphIds.length - 1];
  if (paragraphId === lastInScene) return false;
  if (paragraphId === chapterParagraphIds[chapterParagraphIds.length - 1]) return false;
  if (boundaryAfterParagraphIds.has(paragraphId)) return false;
  return sceneParagraphIds.includes(paragraphId);
}
