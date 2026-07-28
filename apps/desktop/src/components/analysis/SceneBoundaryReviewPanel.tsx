/** Manual scene boundary review panel (CHG-041). */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { analysisApi } from "../../services/analysisApi";
import { ApiError } from "../../services/apiClient";
import { booksApi } from "../../services/booksApi";
import {
  addSceneBoundary,
  computeSceneBoundaryChangeSummary,
  mergeSceneBoundary,
  moveSceneBoundary,
  setSceneIncluded,
  type ScenePartition,
} from "../../services/sceneBoundaryPartitionOps";
import type { Paragraph, SceneBoundaryRevisionSummary } from "../../types";
import "./sceneBoundaryReview.css";

const DIVIDER_LABEL = "──────── 场景分割线 ────────";

type Props = {
  chapterId: number;
  chapterTitle?: string;
  analysisRunId?: number | null;
  journeyRunning?: boolean;
  /** Journey-bound revision id — when stale vs confirmed, show banner. */
  journeyRevisionId?: number | null;
  onExit?: () => void;
  onConfirmed?: (result: {
    journeyStarted: boolean;
    journeyRunId?: number | null;
    revisionId: number;
  }) => void;
};

function revisionScenes(revision: SceneBoundaryRevisionSummary | null | undefined): ScenePartition[] {
  if (!revision?.scenes?.length) return [];
  return revision.scenes.map((scene) => ({
    scene_order: scene.scene_order,
    start_paragraph_id: scene.start_paragraph_id,
    end_paragraph_id: scene.end_paragraph_id,
    included_in_journey: scene.included_in_journey,
  }));
}

function paragraphRangeLabel(
  scene: ScenePartition,
  paragraphIndexById: Map<string, number>,
): string {
  const start = paragraphIndexById.get(scene.start_paragraph_id);
  const end = paragraphIndexById.get(scene.end_paragraph_id);
  if (start == null || end == null) return "—";
  return `${start}—${end}`;
}

export function SceneBoundaryReviewPanel({
  chapterId,
  chapterTitle,
  journeyRunning = false,
  journeyRevisionId = null,
  onExit,
  onConfirmed,
}: Props) {
  const qc = useQueryClient();
  const [editorOpen, setEditorOpen] = useState(false);
  const [draftScenes, setDraftScenes] = useState<ScenePartition[]>([]);
  const [revisionId, setRevisionId] = useState<number | null>(null);
  const [revisionEtag, setRevisionEtag] = useState("");
  const [savedEtag, setSavedEtag] = useState("");
  const [error, setError] = useState<string>();
  const dirtyRef = useRef(false);
  const [dirty, setDirty] = useState(false);

  const markDirty = useCallback((next: boolean) => {
    dirtyRef.current = next;
    setDirty(next);
  }, []);

  const overviewQuery = useQuery({
    queryKey: ["scene-boundaries", chapterId],
    queryFn: () => analysisApi.sceneBoundariesOverview(chapterId),
    retry: false,
  });

  const paragraphsQuery = useQuery({
    queryKey: ["scene-boundary-paragraphs", chapterId],
    queryFn: async () => {
      const items: Paragraph[] = [];
      let offset = 0;
      let hasMore = true;
      while (hasMore) {
        const page = await booksApi.paragraphs(chapterId, offset, 200);
        items.push(...page.items);
        hasMore = page.has_more;
        offset += page.limit;
      }
      return items;
    },
    enabled: editorOpen || Boolean(overviewQuery.data?.awaiting_confirmation),
    retry: false,
  });

  const overview = overviewQuery.data;
  const modelRevision = overview?.model_revision ?? null;
  const confirmedRevision = overview?.confirmed_revision ?? null;
  const modelScenes = useMemo(() => revisionScenes(modelRevision), [modelRevision]);

  const syncDraftFromRevision = useCallback(
    (revision: { revision_id: number; revision_etag: string; scenes: ScenePartition[] }) => {
      setRevisionId(revision.revision_id);
      setRevisionEtag(revision.revision_etag);
      setSavedEtag(revision.revision_etag);
      setDraftScenes(revision.scenes.map((s) => ({ ...s })));
      markDirty(false);
    },
    [markDirty],
  );

  useEffect(() => {
    if (!overview?.draft_revision || editorOpen || journeyRunning) return;
    syncDraftFromRevision({
      revision_id: overview.draft_revision.revision_id,
      revision_etag: overview.draft_revision.revision_etag,
      scenes: revisionScenes(overview.draft_revision),
    });
    setEditorOpen(true);
  }, [overview?.draft_revision, editorOpen, journeyRunning, syncDraftFromRevision]);

  useEffect(() => {
    if (!editorOpen || !overview?.draft_revision) return;
    syncDraftFromRevision({
      revision_id: overview.draft_revision.revision_id,
      revision_etag: overview.draft_revision.revision_etag,
      scenes: revisionScenes(overview.draft_revision),
    });
  }, [editorOpen, overview?.draft_revision, syncDraftFromRevision]);

  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  const paragraphIds = useMemo(
    () => (paragraphsQuery.data || []).map((p) => p.id),
    [paragraphsQuery.data],
  );
  const paragraphIndexById = useMemo(() => {
    const map = new Map<string, number>();
    for (const p of paragraphsQuery.data || []) {
      map.set(p.id, p.paragraph_index);
    }
    return map;
  }, [paragraphsQuery.data]);

  const changeSummary = useMemo(
    () => computeSceneBoundaryChangeSummary(draftScenes, modelScenes),
    [draftScenes, modelScenes],
  );

  const staleJourney =
    journeyRevisionId != null &&
    confirmedRevision?.revision_id != null &&
    journeyRevisionId !== confirmedRevision.revision_id;

  const createDraftMutation = useMutation({
    mutationFn: () => analysisApi.createSceneBoundaryDraft(chapterId),
    onSuccess: (data) => {
      syncDraftFromRevision(data);
      setEditorOpen(true);
      void qc.invalidateQueries({ queryKey: ["scene-boundaries", chapterId] });
    },
    onError: (err) => setError((err as ApiError).message || (err as Error).message),
  });

  const saveDraftMutation = useMutation({
    mutationFn: () => {
      if (!revisionId) throw new Error("缺少草稿修订");
      return analysisApi.saveSceneBoundaryDraft(chapterId, revisionId, {
        expected_etag: revisionEtag,
        scenes: draftScenes,
      });
    },
    onSuccess: (data) => {
      setRevisionEtag(data.revision_etag);
      setSavedEtag(data.revision_etag);
      markDirty(false);
      void qc.invalidateQueries({ queryKey: ["scene-boundaries", chapterId] });
    },
    onError: (err) => setError((err as ApiError).message || (err as Error).message),
  });

  const restoreAiMutation = useMutation({
    mutationFn: () => {
      if (!revisionId) throw new Error("缺少草稿修订");
      return analysisApi.restoreSceneBoundaryAi(chapterId, revisionId);
    },
    onSuccess: (data) => {
      syncDraftFromRevision(data);
      void qc.invalidateQueries({ queryKey: ["scene-boundaries", chapterId] });
    },
    onError: (err) => setError((err as ApiError).message || (err as Error).message),
  });

  const discardMutation = useMutation({
    mutationFn: () => {
      if (!revisionId) throw new Error("缺少草稿修订");
      return analysisApi.discardSceneBoundaryDraft(chapterId, revisionId);
    },
    onSuccess: () => {
      markDirty(false);
      setEditorOpen(false);
      void qc.invalidateQueries({ queryKey: ["scene-boundaries", chapterId] });
    },
    onError: (err) => setError((err as ApiError).message || (err as Error).message),
  });

  const confirmMutation = useMutation({
    mutationFn: (startJourney: boolean) => {
      const targetId = revisionId ?? confirmedRevision?.revision_id;
      const etag = revisionEtag || confirmedRevision?.revision_etag || "";
      if (!targetId || !etag) throw new Error("缺少可确认的修订");
      return analysisApi.confirmSceneBoundary(chapterId, targetId, {
        expected_etag: etag,
        start_journey: startJourney,
        journey_options: {},
      });
    },
    onSuccess: (result) => {
      markDirty(false);
      void qc.invalidateQueries({ queryKey: ["scene-boundaries", chapterId] });
      onConfirmed?.({
        journeyStarted: result.journey_started,
        journeyRunId: result.journey_run_id,
        revisionId: result.revision_id,
      });
    },
    onError: (err) => setError((err as ApiError).message || (err as Error).message),
  });

  const tryExit = () => {
    if (dirtyRef.current) {
      if (!window.confirm("有未保存的场景边界修改，确定离开？")) return;
      markDirty(false);
    }
    onExit?.();
  };

  const openEditor = () => {
    if (overview?.draft_revision) {
      syncDraftFromRevision({
        revision_id: overview.draft_revision.revision_id,
        revision_etag: overview.draft_revision.revision_etag,
        scenes: revisionScenes(overview.draft_revision),
      });
      setEditorOpen(true);
      return;
    }
    createDraftMutation.mutate();
  };

  const sceneBlocks = useMemo(() => {
    if (!paragraphsQuery.data?.length || !draftScenes.length) return [];
    const byId = new Map(paragraphsQuery.data.map((p) => [p.id, p]));
    return draftScenes.map((scene) => {
      const paragraphs: Paragraph[] = [];
      let inRange = false;
      for (const pid of paragraphIds) {
        if (pid === scene.start_paragraph_id) inRange = true;
        if (inRange) {
          const p = byId.get(pid);
          if (p) paragraphs.push(p);
        }
        if (pid === scene.end_paragraph_id) break;
      }
      return { scene, paragraphs };
    });
  }, [draftScenes, paragraphIds, paragraphsQuery.data]);

  const boundaryAfterParagraph = useMemo(() => {
    const set = new Set<string>();
    for (const scene of draftScenes) {
      if (scene.end_paragraph_id !== paragraphIds[paragraphIds.length - 1]) {
        set.add(scene.end_paragraph_id);
      }
    }
    return set;
  }, [draftScenes, paragraphIds]);

  const applyLocalEdit = (next: ScenePartition[]) => {
    setDraftScenes(next);
    markDirty(true);
  };

  if (overviewQuery.isLoading) {
    return (
      <section className="scene-boundary-review" data-testid="scene-boundary-review">
        <p data-testid="scene-boundary-loading">正在加载场景划分…</p>
      </section>
    );
  }

  if (overviewQuery.isError || !overview) {
    return (
      <section className="scene-boundary-review" data-testid="scene-boundary-review">
        <p data-testid="scene-boundary-missing">当前章节没有待确认的场景划分。</p>
        {onExit ? (
          <button type="button" className="secondary" onClick={tryExit}>
            返回
          </button>
        ) : null}
      </section>
    );
  }

  const title = chapterTitle || "本章";
  const aiSceneCount = modelScenes.length;
  const currentSceneCount = editorOpen ? draftScenes.length : aiSceneCount;

  if (journeyRunning) {
    return (
      <section className="scene-boundary-review" data-testid="scene-boundary-review">
        <div className="scene-boundary-readonly" data-testid="scene-boundary-journey-running">
          阅读旅程正在生成中，场景边界暂不可编辑。
        </div>
        {onExit ? (
          <button type="button" className="secondary" onClick={onExit}>
            返回
          </button>
        ) : null}
      </section>
    );
  }

  if (!editorOpen && overview.awaiting_confirmation) {
    return (
      <section className="scene-boundary-review" data-testid="scene-boundary-review">
        {staleJourney ? (
          <div className="scene-boundary-stale-banner" data-testid="scene-boundary-stale-journey">
            当前阅读旅程基于较早的场景划分，确认新划分后将重新生成旅程分析。
          </div>
        ) : null}
        <header className="scene-boundary-review-head">
          <h1>确认场景划分</h1>
          <p data-testid="scene-boundary-waiting-lead">
            StoryLens 已完成场景分析，共识别 {aiSceneCount}{" "}
            个场景。请确认是否采用 AI 划分并开始阅读旅程，或手动调整场景边界。
          </p>
        </header>
        <div className="scene-boundary-waiting-actions">
          <button
            type="button"
            className="primary"
            data-testid="scene-boundary-adopt-ai"
            disabled={confirmMutation.isPending}
            onClick={() => confirmMutation.mutate(true)}
          >
            采用 AI 场景并开始旅程分析
          </button>
          <button
            type="button"
            className="secondary"
            data-testid="scene-boundary-open-editor"
            disabled={createDraftMutation.isPending}
            onClick={openEditor}
          >
            调整场景边界
          </button>
          {onExit ? (
            <button type="button" className="ghost" onClick={tryExit}>
              返回
            </button>
          ) : null}
        </div>
        {error ? (
          <p className="notice error" data-testid="scene-boundary-error">
            {error}
          </p>
        ) : null}
      </section>
    );
  }

  if (!editorOpen) {
    return (
      <section className="scene-boundary-review" data-testid="scene-boundary-review">
        <p data-testid="scene-boundary-idle">当前无需确认场景划分。</p>
        {onExit ? (
          <button type="button" className="secondary" onClick={tryExit}>
            返回
          </button>
        ) : null}
      </section>
    );
  }

  return (
    <section className="scene-boundary-review" data-testid="scene-boundary-review">
      {staleJourney ? (
        <div className="scene-boundary-stale-banner" data-testid="scene-boundary-stale-journey">
          当前阅读旅程基于较早的场景划分，确认新划分后将重新生成旅程分析。
        </div>
      ) : null}

      <header className="scene-boundary-review-head">
        <h1>调整场景边界</h1>
        <div className="scene-boundary-review-status" data-testid="scene-boundary-status">
          <span data-testid="scene-boundary-chapter">{title}</span>
          <span data-testid="scene-boundary-ai-count">AI 场景数：{aiSceneCount}</span>
          <span data-testid="scene-boundary-current-count">当前场景数：{currentSceneCount}</span>
          <span data-testid="scene-boundary-status-text">
            {dirty ? "有未保存修改" : "已保存"}
          </span>
          <span data-testid="scene-boundary-change-summary">
            移动 {changeSummary.moved} · 新增 {changeSummary.added} · 合并{" "}
            {changeSummary.merged} · 排除 {changeSummary.excluded}
          </span>
        </div>
      </header>

      <div className="scene-boundary-body" data-testid="scene-boundary-editor-body">
        {paragraphsQuery.isLoading ? (
          <p data-testid="scene-boundary-paragraphs-loading">正在加载正文…</p>
        ) : null}
        {sceneBlocks.map((block, sceneIndex) => (
          <div key={block.scene.scene_order} data-testid={`scene-boundary-block-${block.scene.scene_order}`}>
            <div className="scene-boundary-toolbar" data-testid={`scene-boundary-toolbar-${block.scene.scene_order}`}>
              <strong>场景 {block.scene.scene_order}</strong>
              <span data-testid={`scene-boundary-range-${block.scene.scene_order}`}>
                段落 {paragraphRangeLabel(block.scene, paragraphIndexById)}
              </span>
              <label data-testid={`scene-boundary-include-${block.scene.scene_order}`}>
                <input
                  type="checkbox"
                  checked={block.scene.included_in_journey}
                  onChange={(event) => {
                    try {
                      applyLocalEdit(
                        setSceneIncluded(
                          draftScenes,
                          block.scene.scene_order,
                          event.target.checked,
                        ),
                      );
                    } catch {
                      setError("无法更新参与旅程分析设置");
                    }
                  }}
                />
                参与旅程分析
              </label>
              <div className="scene-boundary-toolbar-menu">
                <details>
                  <summary aria-label="场景操作">⋯</summary>
                  <ul>
                    {sceneIndex > 0 ? (
                      <li>
                        <button
                          type="button"
                          data-testid={`scene-boundary-merge-prev-${block.scene.scene_order}`}
                          onClick={() => {
                            try {
                              applyLocalEdit(
                                mergeSceneBoundary(draftScenes, sceneIndex - 1, paragraphIds),
                              );
                            } catch {
                              setError("无法合并场景");
                            }
                          }}
                        >
                          与上一场景合并
                        </button>
                      </li>
                    ) : null}
                    {sceneIndex < draftScenes.length - 1 ? (
                      <li>
                        <button
                          type="button"
                          data-testid={`scene-boundary-merge-next-${block.scene.scene_order}`}
                          onClick={() => {
                            try {
                              applyLocalEdit(
                                mergeSceneBoundary(draftScenes, sceneIndex, paragraphIds),
                              );
                            } catch {
                              setError("无法合并场景");
                            }
                          }}
                        >
                          与下一场景合并
                        </button>
                      </li>
                    ) : null}
                    <li>
                      <button
                        type="button"
                        data-testid={`scene-boundary-toggle-include-${block.scene.scene_order}`}
                        onClick={() => {
                          try {
                            applyLocalEdit(
                              setSceneIncluded(
                                draftScenes,
                                block.scene.scene_order,
                                !block.scene.included_in_journey,
                              ),
                            );
                          } catch {
                            setError("无法更新参与旅程分析设置");
                          }
                        }}
                      >
                        {block.scene.included_in_journey ? "排除本场景" : "纳入本场景"}
                      </button>
                    </li>
                  </ul>
                </details>
              </div>
            </div>

            {block.paragraphs.map((paragraph, paraIndex) => {
              const isLastInScene = paraIndex === block.paragraphs.length - 1;
              const isLastParagraph = paragraph.id === paragraphIds[paragraphIds.length - 1];
              const showAdd =
                !isLastInScene &&
                !boundaryAfterParagraph.has(paragraph.id) &&
                paragraph.id !== paragraphIds[paragraphIds.length - 1];

              return (
                <div key={paragraph.id}>
                  <p className="scene-boundary-paragraph" data-testid={`scene-boundary-para-${paragraph.id}`}>
                    {paragraph.raw_text}
                  </p>
                  {showAdd ? (
                    <button
                      type="button"
                      className="ghost scene-boundary-add-split"
                      data-testid={`scene-boundary-add-after-${paragraph.id}`}
                      onClick={() => {
                        try {
                          applyLocalEdit(
                            addSceneBoundary(draftScenes, paragraph.id, paragraphIds),
                          );
                        } catch {
                          setError("无法在此处新增场景分割线");
                        }
                      }}
                    >
                      在此新增场景分割线
                    </button>
                  ) : null}
                  {isLastInScene && !isLastParagraph ? (
                    <div
                      className="scene-boundary-divider"
                      data-testid={`scene-boundary-divider-${sceneIndex}`}
                    >
                      <span className="scene-boundary-divider-label">{DIVIDER_LABEL}</span>
                      <div className="scene-boundary-divider-actions">
                        <button
                          type="button"
                          data-testid={`scene-boundary-move-up-${sceneIndex}`}
                          onClick={() => {
                            try {
                              applyLocalEdit(
                                moveSceneBoundary(draftScenes, sceneIndex, "left", paragraphIds),
                              );
                            } catch {
                              setError("无法上移场景分割线");
                            }
                          }}
                        >
                          上移分割线
                        </button>
                        <button
                          type="button"
                          data-testid={`scene-boundary-move-down-${sceneIndex}`}
                          onClick={() => {
                            try {
                              applyLocalEdit(
                                moveSceneBoundary(draftScenes, sceneIndex, "right", paragraphIds),
                              );
                            } catch {
                              setError("无法下移场景分割线");
                            }
                          }}
                        >
                          下移分割线
                        </button>
                        <button
                          type="button"
                          data-testid={`scene-boundary-delete-divider-${sceneIndex}`}
                          onClick={() => {
                            try {
                              applyLocalEdit(
                                mergeSceneBoundary(draftScenes, sceneIndex, paragraphIds),
                              );
                            } catch {
                              setError("无法删除场景分割线");
                            }
                          }}
                        >
                          删除分割线
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {error ? (
        <p className="notice error" data-testid="scene-boundary-error">
          {error}
        </p>
      ) : null}

      <footer className="scene-boundary-actions" data-testid="scene-boundary-actions">
        <div className="scene-boundary-actions-left">
          <button
            type="button"
            className="secondary"
            data-testid="scene-boundary-restore-ai"
            disabled={restoreAiMutation.isPending || saveDraftMutation.isPending}
            onClick={() => restoreAiMutation.mutate()}
          >
            恢复 AI 划分
          </button>
          <button
            type="button"
            className="secondary"
            data-testid="scene-boundary-save-draft"
            disabled={!dirty || saveDraftMutation.isPending}
            onClick={() => saveDraftMutation.mutate()}
          >
            保存草稿
          </button>
          <button
            type="button"
            className="ghost"
            data-testid="scene-boundary-discard"
            disabled={discardMutation.isPending}
            onClick={() => {
              if (dirty && !window.confirm("放弃未保存的修改？")) return;
              discardMutation.mutate();
            }}
          >
            放弃修改
          </button>
        </div>
        <div className="scene-boundary-actions-right">
          <button
            type="button"
            className="secondary"
            data-testid="scene-boundary-confirm"
            disabled={confirmMutation.isPending || dirty}
            onClick={() => confirmMutation.mutate(false)}
          >
            确认场景
          </button>
          <button
            type="button"
            className="primary"
            data-testid="scene-boundary-confirm-start"
            disabled={confirmMutation.isPending || (dirty && !savedEtag)}
            onClick={() => {
              if (dirty && !window.confirm("有未保存修改，仍要确认并开始旅程？")) return;
              confirmMutation.mutate(true);
            }}
          >
            确认场景并开始旅程分析
          </button>
          {onExit ? (
            <button type="button" className="ghost" data-testid="scene-boundary-exit" onClick={tryExit}>
              返回
            </button>
          ) : null}
        </div>
      </footer>
    </section>
  );
}
