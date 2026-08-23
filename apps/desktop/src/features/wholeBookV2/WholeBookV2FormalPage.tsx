import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Loading } from "../../components/common/States";
import { ApiError } from "../../services/apiClient";
import { getWholeBookV2, getWholeBookV2Progress } from "./api";
import { V2_PROGRESS_LABELS } from "./contracts";
import { WholeBookV2ReportView } from "./presentation/WholeBookV2ReportView";
import type { ModuleKey } from "./presentation/modules";
import { useState } from "react";
import "./formal.css";

/** Deep-link result view: `/books/:bookId/whole-book-v2?runId=…` */
export function WholeBookV2FormalPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const runId = Number(searchParams.get("runId"));
  const moduleParam = (searchParams.get("module") || "overview") as ModuleKey;
  const [activeModule, setActiveModule] = useState<ModuleKey>(moduleParam);

  const result = useQuery({
    queryKey: ["whole-book-v2", runId],
    queryFn: () => getWholeBookV2(runId),
    enabled: Number.isInteger(runId) && runId > 0,
    retry: false,
  });

  const progress = useQuery({
    queryKey: ["whole-book-v2-progress", runId],
    queryFn: () => getWholeBookV2Progress(runId),
    enabled: Number.isInteger(runId) && runId > 0 && !result.data,
    refetchInterval: 3000,
  });

  const onModuleChange = (m: ModuleKey) => {
    setActiveModule(m);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("module", m);
      return next;
    });
  };

  if (!runId) {
    return (
      <section className="wbv2-state">
        <h1>Whole-Book V2</h1>
        <p>请选择一个 V2 分析任务查看正式结果。旧版结果不会伪装成完整 V2。</p>
      </section>
    );
  }

  if (result.data) {
    return (
      <WholeBookV2ReportView
        data={result.data}
        activeModule={activeModule}
        onModuleChange={onModuleChange}
        mode="formal"
      />
    );
  }

  if (progress.data) {
    const stageLabel = V2_PROGRESS_LABELS[progress.data.current_stage] || progress.data.current_action;
    return (
      <section className="wbv2-state">
        <h1>{progress.data.overall_percent.toFixed(0)}%</h1>
        <p>
          {stageLabel} · {progress.data.stage_percent.toFixed(0)}%
        </p>
        <p>{progress.data.current_action}</p>
        <p>
          第 {progress.data.current_chapter}/{progress.data.total_chapters} 章 · 窗口{" "}
          {progress.data.current_window}/{progress.data.total_windows}
        </p>
        <p>
          调用 {progress.data.provider_calls_completed}/{progress.data.provider_calls_estimated}
        </p>
      </section>
    );
  }

  if (result.isError) {
    const legacy =
      result.error instanceof ApiError &&
      (result.error.status === 404 || result.error.code === "WHOLE_BOOK_V2_RESULT_NOT_FOUND");
    return (
      <section className="wbv2-state">
        <h1>{legacy ? "旧版分析结果" : "V2 结果暂不可用"}</h1>
        <p>
          {legacy
            ? "这是旧版全书分析结果，需要重新分析以生成 V2 完整结果。"
            : "该任务可能是 partial，或尚未生成 V2 结果。"}
        </p>
      </section>
    );
  }

  return (
    <section className="wbv2-state">
      <h1>正在读取 Whole-Book V2</h1>
      <Loading />
    </section>
  );
}
