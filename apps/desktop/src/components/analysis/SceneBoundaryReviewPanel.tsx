/** Manual scene boundary review panel (CHG-041). */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { analysisApi } from "../../services/analysisApi";
import { booksApi } from "../../services/booksApi";
import {
  mapSceneBoundaryError,
  SCENE_BOUNDARY_CONFLICT_CODE,
} from "../../services/sceneBoundaryErrors";
import {
  addSceneBoundary,
  canSplitAfterParagraph,
  computeSceneBoundaryChangeSummary,
  mergeSceneBoundary,
  moveSceneBoundary,
  setSceneIncluded,
  type ScenePartition,
} from "../../services/sceneBoundaryPartitionOps";
import type { Paragraph, SceneBoundaryRevisionSummary, SceneBoundariesOverview, ScenePartitionItem } from "../../types";
import "./sceneBoundaryReview.css";

const DIVIDER_LABEL = "──────── 场景分割线 ────────";

type DraftSnapshot = {
  revision_id: number;
  revision_etag: string;
  boundary_hash?: string;
  scenes: ScenePartition[];
  status?: string;
  updated_at?: string | null;
};

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

function toDraftSummary(snapshot: DraftSnapshot, base?: SceneBoundaryRevisionSummary | null) {
  return {
    revision_id: snapshot.revision_id,
    revision_number: base?.revision_number ?? 0,
    status: snapshot.status || base?.status || "draft",
    source: base?.source || "user",
    revision_etag: snapshot.revision_etag,
    boundary_hash: snapshot.boundary_hash || base?.boundary_hash || "",
    chapter_text_hash: base?.chapter_text_hash || "",
    scenes: snapshot.scenes.map((s) => ({ ...s })),
    confirmed_at: base?.confirmed_at ?? null,
    updated_at: snapshot.updated_at ?? null,
  } as SceneBoundaryRevisionSummary;
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
  const [mode, setMode] = useState<"edit" | "confirmed_readonly">("edit");
  const [draftScenes, setDraftScenes] = useState<ScenePartition[]>([]);
  const [revisionId, setRevisionId] = useState<number | null>(null);
  const [revisionEtag, setRevisionEtag] = useState("");
  const [boundaryHash, setBoundaryHash] = useState("");
  const [error, setError] = useState<string>();
  const [errorCode, setErrorCode] = useState<string>();
  const [successMessage, setSuccessMessage] = useState<string>();
  const [journeyStartFailed, setJourneyStartFailed] = useState(false);
  const [journeyFailReason, setJourneyFailReason] = useState<string>();
  const [journeyRunIdState, setJourneyRunIdState] = useState<number | null>(null);
  const [journeyStatusState, setJourneyStatusState] = useState<string | null>(null);
  const [conflictOpen, setConflictOpen] = useState(false);
  const [showTechDetails, setShowTechDetails] = useState(false);
  const dirtyRef = useRef(false);
  const [dirty, setDirty] = useState(false);
  const persistChainRef = useRef(Promise.resolve());
  const draftRef = useRef<{ revisionId: number | null; etag: string; scenes: ScenePartition[] }>({
    revisionId: null,
    etag: "",
    scenes: [],
  });

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
    enabled: editorOpen || mode === "confirmed_readonly" || Boolean(overviewQuery.data?.awaiting_confirmation),
    retry: false,
  });

  const overview = overviewQuery.data;
  const modelRevision = overview?.model_revision ?? null;
  const confirmedRevision = overview?.confirmed_revision ?? null;
  const modelScenes = useMemo(() => revisionScenes(modelRevision), [modelRevision]);

  const applyDraftSnapshot = useCallback(
    (snapshot: DraftSnapshot, opts?: { dirty?: boolean; openEditor?: boolean }) => {
      draftRef.current = {
        revisionId: snapshot.revision_id,
        etag: snapshot.revision_etag,
        scenes: snapshot.scenes.map((s) => ({ ...s })),
      };
      setRevisionId(snapshot.revision_id);
      setRevisionEtag(snapshot.revision_etag);
      setBoundaryHash(snapshot.boundary_hash || "");
      setDraftScenes(snapshot.scenes.map((s) => ({ ...s })));
      markDirty(Boolean(opts?.dirty));
      if (opts?.openEditor) setEditorOpen(true);
    },
    [markDirty],
  );

  const patchOverviewDraft = useCallback(
    (snapshot: DraftSnapshot | null) => {
      qc.setQueryData<SceneBoundariesOverview>(["scene-boundaries", chapterId], (prev) => {
        if (!prev) return prev;
        if (!snapshot) {
          return { ...prev, draft_revision: null, awaiting_confirmation: false };
        }
        const packed = toDraftSummary(snapshot, prev.draft_revision);
        return {
          ...prev,
          draft_revision: packed,
          awaiting_confirmation: prev.awaiting_confirmation || snapshot.status === "draft",
        };
      });
    },
    [chapterId, qc],
  );

  const patchOverviewConfirmed = useCallback(
    (snapshot: DraftSnapshot) => {
      qc.setQueryData<SceneBoundariesOverview>(["scene-boundaries", chapterId], (prev) => {
        if (!prev) return prev;
        const packed = toDraftSummary(
          { ...snapshot, status: "confirmed" },
          prev.confirmed_revision || prev.draft_revision || prev.model_revision,
        );
        return {
          ...prev,
          draft_revision: null,
          confirmed_revision: packed,
          awaiting_confirmation: false,
        };
      });
    },
    [chapterId, qc],
  );

  // Open existing draft once; do not re-sync from overview after local/mutation updates.
  useEffect(() => {
    if (!overview?.draft_revision || editorOpen || journeyRunning || mode === "confirmed_readonly") {
      return;
    }
    applyDraftSnapshot(
      {
        revision_id: overview.draft_revision.revision_id,
        revision_etag: overview.draft_revision.revision_etag,
        boundary_hash: overview.draft_revision.boundary_hash,
        scenes: revisionScenes(overview.draft_revision),
        status: overview.draft_revision.status,
      },
      { openEditor: true },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional one-shot open from server draft
  }, [overview?.draft_revision?.revision_id]);

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

  const handleMappedError = useCallback((err: unknown) => {
    const mapped = mapSceneBoundaryError(err);
    setError(mapped.userMessage);
    setErrorCode(mapped.code);
    if (mapped.isConflict) setConflictOpen(true);
  }, []);

  const createDraftMutation = useMutation({
    mutationFn: () => analysisApi.createSceneBoundaryDraft(chapterId),
    onSuccess: (data) => {
      const raw = data as {
        revision_id: number;
        revision_etag: string;
        scenes: ScenePartitionItem[];
        boundary_hash?: string;
        status?: string;
        updated_at?: string | null;
      };
      const snapshot: DraftSnapshot = {
        revision_id: raw.revision_id,
        revision_etag: raw.revision_etag,
        boundary_hash: raw.boundary_hash || undefined,
        scenes: raw.scenes.map((s) => ({ ...s })),
        status: raw.status || "draft",
        updated_at: raw.updated_at,
      };
      applyDraftSnapshot(snapshot, { openEditor: true });
      patchOverviewDraft(snapshot);
      setMode("edit");
      setSuccessMessage(undefined);
      setError(undefined);
      setErrorCode(undefined);
    },
    onError: handleMappedError,
  });

  const persistDraft = useCallback(
    async (scenes: ScenePartition[]) => {
      const current = draftRef.current;
      if (!current.revisionId || !current.etag) throw new Error("缺少草稿修订");
      const data = await analysisApi.saveSceneBoundaryDraft(chapterId, current.revisionId, {
        expected_etag: current.etag,
        scenes,
      });
      const snapshot: DraftSnapshot = {
        revision_id: data.revision_id,
        revision_etag: data.revision_etag,
        boundary_hash: data.boundary_hash,
        scenes: (data.scenes?.length ? data.scenes : scenes).map((s) => ({ ...s })),
        status: data.status || "draft",
        updated_at: data.updated_at,
      };
      applyDraftSnapshot(snapshot);
      patchOverviewDraft(snapshot);
      return snapshot;
    },
    [applyDraftSnapshot, chapterId, patchOverviewDraft],
  );

  const enqueuePersist = useCallback(
    (scenes: ScenePartition[], successText?: string) => {
      setDraftScenes(scenes);
      draftRef.current = { ...draftRef.current, scenes: scenes.map((s) => ({ ...s })) };
      markDirty(true);
      setError(undefined);
      setErrorCode(undefined);
      setSuccessMessage(undefined);
      const run = persistChainRef.current.then(async () => {
        try {
          await persistDraft(scenes);
          if (successText) setSuccessMessage(successText);
        } catch (err) {
          handleMappedError(err);
          throw err;
        }
      });
      persistChainRef.current = run.catch(() => undefined);
      return run;
    },
    [handleMappedError, markDirty, persistDraft],
  );

  const splitAfterParagraph = useCallback(
    (paragraphId: string, sceneOrder: number) => {
      const current = draftRef.current;
      if (!current.revisionId || !current.etag) {
        setError("缺少草稿修订");
        return;
      }
      const clientRequestId =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `split-${Date.now()}-${paragraphId}`;
      markDirty(true);
      setError(undefined);
      setErrorCode(undefined);
      setSuccessMessage(undefined);
      const run = persistChainRef.current.then(async () => {
        try {
          const data = await analysisApi.splitSceneBoundaryDraft(chapterId, current.revisionId!, {
            expected_etag: draftRef.current.etag,
            boundary_after_paragraph_id: paragraphId,
            client_request_id: clientRequestId,
            scene_order: sceneOrder,
          });
          const snapshot: DraftSnapshot = {
            revision_id: data.revision_id,
            revision_etag: data.revision_etag,
            boundary_hash: data.boundary_hash,
            scenes: data.scenes.map((s) => ({ ...s })),
            status: data.status || "draft",
            updated_at: data.updated_at,
          };
          applyDraftSnapshot(snapshot);
          patchOverviewDraft(snapshot);
          setSuccessMessage(data.already_split ? "这里已经是场景边界" : "已新增一个场景。");
        } catch (err) {
          // Fallback: optimistic local split + bulk save if dedicated endpoint unavailable.
          const mapped = mapSceneBoundaryError(err);
          if (mapped.code === "HTTP_ERROR" || mapped.code == null) {
            try {
              const next = addSceneBoundary(draftRef.current.scenes, paragraphId, paragraphIds);
              await persistDraft(next);
              setSuccessMessage("已新增一个场景。");
              return;
            } catch (fallbackErr) {
              handleMappedError(fallbackErr);
              throw fallbackErr;
            }
          }
          handleMappedError(err);
          throw err;
        }
      });
      persistChainRef.current = run.catch(() => undefined);
      return run;
    },
    [
      applyDraftSnapshot,
      chapterId,
      handleMappedError,
      markDirty,
      paragraphIds,
      patchOverviewDraft,
      persistDraft,
    ],
  );

  const mergeAtBoundary = useCallback(
    (boundaryIndex: number) => {
      const left = draftScenes[boundaryIndex];
      const right = draftScenes[boundaryIndex + 1];
      if (!left || !right) {
        setError("无法删除场景分割线");
        return;
      }
      let included: boolean | undefined;
      if (left.included_in_journey !== right.included_in_journey) {
        const keep = window.confirm(
          "两侧场景的旅程参与状态不同。\n确定：合并后参与旅程分析\n取消：合并后不参与旅程分析",
        );
        included = keep;
      }
      try {
        applyLocalEdit(
          mergeSceneBoundary(draftScenes, boundaryIndex, paragraphIds, included),
          "已合并场景。",
        );
      } catch (err) {
        const mapped = mapSceneBoundaryError(err);
        setError(mapped.userMessage);
        setErrorCode(mapped.code);
      }
    },
    [draftScenes, paragraphIds],
  );

  const saveDraftMutation = useMutation({
    mutationFn: async () => persistDraft(draftRef.current.scenes),
    onSuccess: () => {
      setSuccessMessage("草稿已保存");
    },
    onError: handleMappedError,
  });

  const restoreAiMutation = useMutation({
    mutationFn: async () => {
      const current = draftRef.current;
      if (!current.revisionId) throw new Error("缺少草稿修订");
      return analysisApi.restoreSceneBoundaryAi(chapterId, current.revisionId);
    },
    onSuccess: (data) => {
      const snapshot: DraftSnapshot = {
        revision_id: data.revision_id,
        revision_etag: data.revision_etag,
        boundary_hash: data.boundary_hash || undefined,
        scenes: data.scenes.map((s) => ({ ...s })),
        status: data.status || "draft",
        updated_at: data.updated_at,
      };
      applyDraftSnapshot(snapshot);
      patchOverviewDraft(snapshot);
      setSuccessMessage("已恢复为 AI 划分");
    },
    onError: handleMappedError,
  });

  const discardMutation = useMutation({
    mutationFn: async () => {
      const current = draftRef.current;
      if (!current.revisionId) throw new Error("缺少草稿修订");
      return analysisApi.discardSceneBoundaryDraft(chapterId, current.revisionId);
    },
    onSuccess: () => {
      markDirty(false);
      setEditorOpen(false);
      draftRef.current = { revisionId: null, etag: "", scenes: [] };
      patchOverviewDraft(null);
      void qc.invalidateQueries({ queryKey: ["scene-boundaries", chapterId] });
    },
    onError: handleMappedError,
  });

  const confirmMutation = useMutation({
    mutationFn: async (startJourney: boolean) => {
      // Flush any in-flight boundary persists before confirm.
      await persistChainRef.current;
      const current = draftRef.current;
      const targetId = current.revisionId ?? confirmedRevision?.revision_id ?? null;
      const etag = current.etag || confirmedRevision?.revision_etag || "";
      if (!targetId || !etag) throw new Error("缺少可确认的修订");
      if (dirtyRef.current && current.revisionId) {
        await persistDraft(current.scenes);
      }
      const latest = draftRef.current;
      return analysisApi.confirmSceneBoundary(chapterId, latest.revisionId || targetId, {
        expected_etag: latest.etag || etag,
        start_journey: startJourney,
        journey_options: {},
      });
    },
    onSuccess: (result, startJourney) => {
      markDirty(false);
      setConflictOpen(false);
      setError(undefined);
      setErrorCode(undefined);
      const started = Boolean(result.journey_started);
      const failedStart = Boolean(startJourney) && !started;
      setJourneyStartFailed(failedStart);
      setJourneyFailReason(
        failedStart
          ? result.journey_error_message ||
              (result.journey_error_code === "JOURNEY_TASK_ALREADY_ACTIVE"
                ? "当前存在运行中的任务。"
                : "阅读旅程任务未能启动。")
          : undefined,
      );
      setJourneyRunIdState(result.journey_run_id ?? null);
      setJourneyStatusState(result.journey_status ?? null);
      const snapshot: DraftSnapshot = {
        revision_id: result.revision_id,
        revision_etag: result.revision_etag,
        boundary_hash: result.boundary_hash,
        scenes: draftRef.current.scenes,
        status: "confirmed",
      };
      draftRef.current = {
        revisionId: result.revision_id,
        etag: result.revision_etag,
        scenes: draftRef.current.scenes,
      };
      setRevisionId(result.revision_id);
      setRevisionEtag(result.revision_etag);
      setBoundaryHash(result.boundary_hash);
      patchOverviewConfirmed(snapshot);
      setMode("confirmed_readonly");
      setEditorOpen(false);
      setSuccessMessage(
        startJourney && started
          ? "场景划分已确认，正在进入阅读旅程"
          : startJourney && !started
            ? "场景划分已确认"
            : "场景划分已确认",
      );
      onConfirmed?.({
        journeyStarted: started,
        journeyRunId: result.journey_run_id,
        revisionId: result.revision_id,
      });
    },
    onError: handleMappedError,
  });

  const busy =
    createDraftMutation.isPending ||
    saveDraftMutation.isPending ||
    restoreAiMutation.isPending ||
    discardMutation.isPending ||
    confirmMutation.isPending;

  const tryExit = () => {
    if (dirtyRef.current) {
      if (!window.confirm("有未保存的场景边界修改，确定离开？")) return;
      markDirty(false);
    }
    onExit?.();
  };

  const reloadLatestDraft = async () => {
    if (dirtyRef.current) {
      if (
        !window.confirm(
          "重新加载将丢弃当前页面上尚未同步的本地修改。确定继续？",
        )
      ) {
        return;
      }
    }
    setConflictOpen(false);
    setError(undefined);
    setErrorCode(undefined);
    const fresh = await overviewQuery.refetch();
    const draft = fresh.data?.draft_revision;
    if (draft) {
      applyDraftSnapshot(
        {
          revision_id: draft.revision_id,
          revision_etag: draft.revision_etag,
          boundary_hash: draft.boundary_hash,
          scenes: revisionScenes(draft),
          status: draft.status,
        },
        { openEditor: true },
      );
      setMode("edit");
      return;
    }
    markDirty(false);
    setEditorOpen(false);
    setMode("edit");
  };

  const openEditor = () => {
    if (overview?.draft_revision) {
      applyDraftSnapshot(
        {
          revision_id: overview.draft_revision.revision_id,
          revision_etag: overview.draft_revision.revision_etag,
          boundary_hash: overview.draft_revision.boundary_hash,
          scenes: revisionScenes(overview.draft_revision),
          status: overview.draft_revision.status,
        },
        { openEditor: true },
      );
      setMode("edit");
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

  const applyLocalEdit = (next: ScenePartition[], successText?: string) => {
    void enqueuePersist(next, successText);
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
  const currentSceneCount =
    editorOpen || mode === "confirmed_readonly" ? draftScenes.length : aiSceneCount;

  if (journeyRunning && mode !== "confirmed_readonly") {
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

  if (mode === "confirmed_readonly") {
    const running =
      journeyStatusState === "queued" ||
      journeyStatusState === "running" ||
      journeyStatusState === "scene_profiles_running" ||
      journeyStatusState === "chapter_synthesis_running";
    const succeeded = journeyStatusState === "succeeded" && journeyRunIdState != null;
    let primaryLabel = "生成阅读旅程";
    let primaryTestId = "scene-boundary-start-journey";
    if (journeyStartFailed) {
      primaryLabel = "重新尝试生成阅读旅程";
      primaryTestId = "scene-boundary-retry-journey";
    } else if (running) {
      primaryLabel = "查看阅读旅程进度";
      primaryTestId = "scene-boundary-view-journey-progress";
    } else if (succeeded) {
      primaryLabel = "查看阅读旅程";
      primaryTestId = "scene-boundary-view-journey";
    }
    return (
      <section className="scene-boundary-review" data-testid="scene-boundary-review">
        <header className="scene-boundary-review-head">
          <h1>场景划分已确认</h1>
          {successMessage ? (
            <p className="notice success" data-testid="scene-boundary-success" role="status">
              {successMessage}
            </p>
          ) : null}
        </header>
        <div className="scene-boundary-readonly" data-testid="scene-boundary-confirmed-readonly">
          <p>已确认修订 #{revisionId ?? confirmedRevision?.revision_id}</p>
          <p data-testid="scene-boundary-confirmed-count">
            场景数：{currentSceneCount || revisionScenes(confirmedRevision).length}
          </p>
          {boundaryHash ? (
            <p data-testid="scene-boundary-confirmed-hash">边界指纹：{boundaryHash.slice(0, 12)}…</p>
          ) : null}
        </div>
        {journeyStartFailed ? (
          <div className="notice error" data-testid="scene-boundary-journey-failed">
            <p>阅读旅程任务未能启动。</p>
            <p data-testid="scene-boundary-journey-fail-reason">
              {journeyFailReason || "请检查配置后重试。"}
            </p>
          </div>
        ) : null}
        <footer className="scene-boundary-actions">
          <button
            type="button"
            className="primary"
            data-testid={primaryTestId}
            disabled={confirmMutation.isPending}
            onClick={() => {
              if (running || succeeded) {
                onConfirmed?.({
                  journeyStarted: true,
                  journeyRunId: journeyRunIdState,
                  revisionId: revisionId || confirmedRevision?.revision_id || 0,
                });
                return;
              }
              confirmMutation.mutate(true);
            }}
          >
            {confirmMutation.isPending ? "启动中…" : primaryLabel}
          </button>
          <button
            type="button"
            className="secondary"
            data-testid="scene-boundary-readjust"
            disabled={createDraftMutation.isPending || confirmMutation.isPending}
            onClick={() => createDraftMutation.mutate()}
          >
            重新调整场景
          </button>
          {onExit ? (
            <button type="button" className="ghost" data-testid="scene-boundary-back-reading" onClick={onExit}>
              返回正文阅读
            </button>
          ) : null}
        </footer>
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
            已生成场景划分建议，共 {aiSceneCount}{" "}
            个场景。请确认是否采用，或手动调整场景边界。
          </p>
        </header>
        <div className="scene-boundary-waiting-actions">
          <button
            type="button"
            className="primary"
            data-testid="scene-boundary-adopt-ai"
            disabled={confirmMutation.isPending}
            onClick={() => {
              const target = overview.confirmed_revision || overview.model_revision;
              if (target) {
                draftRef.current = {
                  revisionId: target.revision_id,
                  etag: target.revision_etag,
                  scenes: revisionScenes(target),
                };
                setRevisionId(target.revision_id);
                setRevisionEtag(target.revision_etag);
              }
              confirmMutation.mutate(true);
            }}
          >
            {confirmMutation.isPending
              ? "确认中…"
              : `确认这 ${aiSceneCount} 个场景并开始分析`}
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
          <div className="notice error" data-testid="scene-boundary-error">
            <p>{error}</p>
            {errorCode ? (
              <details data-testid="scene-boundary-error-tech">
                <summary>技术详情</summary>
                <code>{errorCode}</code>
              </details>
            ) : null}
          </div>
        ) : null}
      </section>
    );
  }

  if (!editorOpen) {
    return (
      <section className="scene-boundary-review" data-testid="scene-boundary-review">
        <p data-testid="scene-boundary-idle">当前无需确认场景划分。</p>
        {confirmedRevision ? (
          <button type="button" className="secondary" data-testid="scene-boundary-readjust" onClick={openEditor}>
            重新调整场景
          </button>
        ) : null}
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
            {busy && dirty ? "保存中…" : dirty ? "有未保存修改" : "已保存"}
          </span>
          <span data-testid="scene-boundary-etag" data-revision-etag={revisionEtag}>
            ETag {revisionEtag.slice(0, 8) || "—"}
          </span>
          <span data-testid="scene-boundary-change-summary">
            移动 {changeSummary.moved} · 新增 {changeSummary.added} · 合并{" "}
            {changeSummary.merged} · 排除 {changeSummary.excluded}
          </span>
        </div>
      </header>

      {successMessage ? (
        <p className="notice success" data-testid="scene-boundary-success" role="status">
          {successMessage}
        </p>
      ) : null}

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
                  disabled={busy}
                  onChange={(event) => {
                    try {
                      applyLocalEdit(
                        setSceneIncluded(draftScenes, block.scene.scene_order, event.target.checked),
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
                          disabled={busy}
                          onClick={() => {
                            mergeAtBoundary(sceneIndex - 1);
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
                          disabled={busy}
                          onClick={() => {
                            mergeAtBoundary(sceneIndex);
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
                        disabled={busy}
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
              const sceneParaIds = block.paragraphs.map((item) => item.id);
              const isLastInScene = paraIndex === block.paragraphs.length - 1;
              const isLastParagraph = paragraph.id === paragraphIds[paragraphIds.length - 1];
              const showAdd = canSplitAfterParagraph({
                paragraphId: paragraph.id,
                sceneParagraphIds: sceneParaIds,
                chapterParagraphIds: paragraphIds,
                boundaryAfterParagraphIds: boundaryAfterParagraph,
              });

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
                      disabled={busy}
                      onClick={() => {
                        void splitAfterParagraph(paragraph.id, block.scene.scene_order);
                      }}
                    >
                      ＋ 在此拆分为新场景
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
                          disabled={busy}
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
                          disabled={busy}
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
                          disabled={busy}
                          onClick={() => {
                            mergeAtBoundary(sceneIndex);
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

      {error && !conflictOpen ? (
        <div className="notice error" data-testid="scene-boundary-error">
          <p>{error}</p>
          {errorCode ? (
            <details data-testid="scene-boundary-error-tech" open={showTechDetails}>
              <summary onClick={() => setShowTechDetails((v) => !v)}>技术详情</summary>
              <code>{errorCode}</code>
            </details>
          ) : null}
        </div>
      ) : null}

      {conflictOpen ? (
        <div
          className="scene-boundary-conflict-dialog"
          role="dialog"
          aria-modal="true"
          data-testid="scene-boundary-conflict-dialog"
        >
          <h2>场景草稿已更新</h2>
          <p>
            当前场景草稿已在其他窗口或操作中发生变化。请重新加载最新版本后继续。
          </p>
          {dirty ? (
            <p className="notice" data-testid="scene-boundary-conflict-dirty-warning">
              重新加载会丢弃当前页面尚未同步的本地修改。
            </p>
          ) : null}
          <div className="scene-boundary-waiting-actions">
            <button
              type="button"
              className="primary"
              data-testid="scene-boundary-conflict-reload"
              onClick={() => void reloadLatestDraft()}
            >
              重新加载最新草稿
            </button>
            <button
              type="button"
              className="secondary"
              data-testid="scene-boundary-conflict-keep"
              onClick={() => setConflictOpen(false)}
            >
              保留当前页面
            </button>
          </div>
          <details data-testid="scene-boundary-error-tech">
            <summary>技术详情</summary>
            <code>{errorCode || SCENE_BOUNDARY_CONFLICT_CODE}</code>
          </details>
        </div>
      ) : null}

      <footer className="scene-boundary-actions" data-testid="scene-boundary-actions">
        <div className="scene-boundary-actions-left">
          <button
            type="button"
            className="secondary"
            data-testid="scene-boundary-restore-ai"
            disabled={busy}
            onClick={() => restoreAiMutation.mutate()}
          >
            恢复 AI 划分
          </button>
          <button
            type="button"
            className="secondary"
            data-testid="scene-boundary-save-draft"
            disabled={!dirty || busy}
            onClick={() => saveDraftMutation.mutate()}
          >
            {saveDraftMutation.isPending ? "保存中…" : "保存草稿"}
          </button>
          <button
            type="button"
            className="ghost"
            data-testid="scene-boundary-discard"
            disabled={busy}
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
            disabled={busy || confirmMutation.isPending}
            title="保存并确认当前场景划分，暂不生成阅读旅程。"
            onClick={() => confirmMutation.mutate(false)}
          >
            {confirmMutation.isPending && confirmMutation.variables === false
              ? "确认中…"
              : "仅确认场景划分"}
          </button>
          <button
            type="button"
            className="primary"
            data-testid="scene-boundary-confirm-start"
            disabled={busy || confirmMutation.isPending}
            title="确认当前场景划分，并立即开始生成阅读旅程。"
            onClick={() => confirmMutation.mutate(true)}
          >
            {confirmMutation.isPending && confirmMutation.variables === true
              ? "确认中…"
              : `确认这 ${currentSceneCount} 个场景并开始分析`}
          </button>
          {onExit ? (
            <button type="button" className="ghost" data-testid="scene-boundary-exit" onClick={tryExit}>
              离开
            </button>
          ) : null}
        </div>
      </footer>
    </section>
  );
}
