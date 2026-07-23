import { useMemo } from "react";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import {
  HOOK_RESOLUTION_CONCLUSION_TITLE,
  HOOK_RESOLUTION_CONFLICT_TITLE,
  HOOK_RESOLUTION_LIST_TITLE,
  HOOK_RESOLUTION_OVERVIEW_TITLE,
  buildHookResolutionModel,
  type HookResolutionRow,
} from "./hookResolutionModel";
import "./hookPayoffTimeline.css";

type Props = {
  visualization: ReaderJourneyVisualization;
  selectedLoopId?: string | null;
  selectedSceneOrdinal?: number | null;
  onSelectLoop?: (loopId: string, sceneOrdinal: number) => void;
  onLocateEvidence?: (paragraphId: string) => void;
};

const SCENE_COL_MIN = 56;
const MAX_VISIBLE_LANES = 6;

function sceneAxis(maxScene: number): number[] {
  return Array.from({ length: maxScene }, (_, i) => i + 1);
}

function lanePercent(scene: number, maxScene: number): number {
  if (maxScene <= 1) return 0;
  return ((scene - 1) / (maxScene - 1)) * 100;
}

/** Hook resolution result page: conclusion → conflicts → bus → list. */
export function HookPayoffTimeline({
  visualization,
  selectedLoopId = null,
  selectedSceneOrdinal = null,
  onSelectLoop,
  onLocateEvidence,
}: Props) {
  const model = useMemo(() => buildHookResolutionModel(visualization), [visualization]);
  const scenes = sceneAxis(model.max_scene);
  const trackMinWidth = Math.max(420, model.max_scene * SCENE_COL_MIN + 140);

  const selectRow = (row: HookResolutionRow) => {
    onSelectLoop?.(row.loop_id, row.locate_scene);
  };

  const locateRow = (row: HookResolutionRow) => {
    const pid = row.evidence_paragraph_ids[0];
    if (pid && onLocateEvidence) {
      onLocateEvidence(pid);
    }
    selectRow(row);
  };

  if (model.empty) {
    return (
      <div
        className="hook-resolution-panel"
        data-testid="hook-payoff-timeline"
        data-layout="hook-resolution"
        data-empty="true"
      >
        <section
          className="hook-resolution-conclusion"
          data-testid="hook-resolution-conclusion"
        >
          <h3>{HOOK_RESOLUTION_CONCLUSION_TITLE}</h3>
          <p data-testid="hook-resolution-verdict">本章未识别出明确钩子。</p>
        </section>
        <p className="hook-resolution-empty" data-testid="hook-resolution-empty">
          暂无钩子可展示，不绘制总览图。
        </p>
      </div>
    );
  }

  return (
    <div
      className="hook-resolution-panel"
      data-testid="hook-payoff-timeline"
      data-layout="hook-resolution"
      data-empty="false"
    >
      <section
        className="hook-resolution-conclusion"
        data-testid="hook-resolution-conclusion"
      >
        <h3>{HOOK_RESOLUTION_CONCLUSION_TITLE}</h3>
        <ul className="hook-resolution-stats" data-testid="hook-payoff-stats">
          <li data-testid="hook-stat-established">建立钩子 {model.stats.established}</li>
          <li data-testid="hook-stat-resolved">已回收 {model.stats.resolved}</li>
          <li data-testid="hook-stat-partial">部分回收 {model.stats.partial}</li>
          <li data-testid="hook-stat-unresolved">未回收 {model.stats.unresolved}</li>
          <li data-testid="hook-stat-conflict">有冲突 {model.stats.conflict}</li>
        </ul>
        <p className="hook-resolution-verdict" data-testid="hook-resolution-verdict">
          {model.verdict}
        </p>
      </section>

      {model.conflicts.length > 0 ? (
        <section
          className="hook-resolution-conflicts"
          data-testid="hook-resolution-conflicts"
        >
          <h3>{HOOK_RESOLUTION_CONFLICT_TITLE}</h3>
          <p data-testid="hook-resolution-conflict-summary">
            本章有 {model.conflicts.length} 个钩子存在判定冲突
          </p>
          <ul data-testid="hook-resolution-conflict-list">
            {model.conflicts.map((item) => (
              <li key={item.loop_id} data-testid="hook-resolution-conflict-item">
                <strong>
                  {item.loop_id} · {item.short_title}
                </strong>
                <span>主结论：{item.main_label}</span>
                <span>冲突点：{item.conflict_point}</span>
                <span>原因：{item.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section
        className="hook-resolution-overview"
        data-testid="hook-resolution-overview"
      >
        <h3>{HOOK_RESOLUTION_OVERVIEW_TITLE}</h3>
        <div className="hook-resolution-bus-scroll" data-testid="hook-payoff-rows-scroll">
          <div
            className="hook-resolution-bus-track"
            data-testid="hook-payoff-rows-track"
            style={{ minWidth: trackMinWidth }}
          >
            <div className="hook-resolution-axis" data-testid="hook-resolution-axis">
              <span className="hook-resolution-axis-spacer" />
              <div className="hook-resolution-axis-scenes">
                {scenes.map((s) => (
                  <span key={s} className="hook-resolution-axis-tick">
                    S{s}
                  </span>
                ))}
              </div>
              <span className="hook-resolution-axis-end" />
            </div>
            <div
              className="hook-resolution-lanes"
              data-testid="hook-resolution-lanes"
              data-max-visible={MAX_VISIBLE_LANES}
            >
              {model.rows.map((row) => {
                const active =
                  selectedLoopId != null
                    ? row.loop_id === selectedLoopId
                    : selectedSceneOrdinal != null
                      ? row.open_scene === selectedSceneOrdinal ||
                        row.resolve_scene === selectedSceneOrdinal
                      : false;
                const startPct = lanePercent(row.open_scene, model.max_scene);
                const endScene = row.resolve_scene ?? model.max_scene;
                const endPct = lanePercent(endScene, model.max_scene);
                const left = Math.min(startPct, endPct);
                const width = Math.max(Math.abs(endPct - startPct), 2);
                return (
                  <button
                    type="button"
                    key={row.loop_id}
                    className={`hook-resolution-lane${active ? " is-active" : ""}`}
                    data-testid="hook-payoff-loop-row"
                    data-loop-id={row.loop_id}
                    data-main-status={row.main_status}
                    data-line-style={row.line_style}
                    data-has-conflict={row.has_conflict ? "true" : "false"}
                    title={row.full_title}
                    onClick={() => selectRow(row)}
                  >
                    <span className="hook-resolution-lane-label" title={row.full_title}>
                      {row.short_title}
                    </span>
                    <span className="hook-resolution-lane-rail">
                      <span
                        className={`hook-resolution-line hook-resolution-line--${row.line_style}`}
                        style={{ left: `${left}%`, width: `${width}%` }}
                        data-testid="hook-resolution-line"
                      />
                      <span
                        className="hook-resolution-node hook-resolution-node--open"
                        style={{ left: `${startPct}%` }}
                        data-testid="hook-resolution-node-open"
                        title={`提出于 S${row.open_scene}`}
                      >
                        提
                      </span>
                      {row.resolve_scene != null ? (
                        <span
                          className="hook-resolution-node hook-resolution-node--resolve"
                          style={{ left: `${endPct}%` }}
                          data-testid="hook-resolution-node-resolve"
                          title={`回收于 S${row.resolve_scene}`}
                        >
                          回
                        </span>
                      ) : (
                        <span
                          className="hook-resolution-node hook-resolution-node--open-end"
                          style={{ left: `${endPct}%` }}
                          data-testid="hook-resolution-node-unresolved"
                          title="本章未回收"
                        >
                          未
                        </span>
                      )}
                    </span>
                    <span className="hook-resolution-lane-status">
                      {row.main_label}
                      {row.has_conflict ? " · 冲突" : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      <section className="hook-resolution-list" data-testid="hook-resolution-list">
        <h3>{HOOK_RESOLUTION_LIST_TITLE}</h3>
        <div className="hook-resolution-table-wrap">
          <table className="hook-resolution-table" data-testid="hook-resolution-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>钩子</th>
                <th>提出</th>
                <th>主结论</th>
                <th>回收位置</th>
                <th>冲突</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {model.rows.map((row) => (
                <tr
                  key={row.loop_id}
                  data-testid="hook-resolution-list-row"
                  data-loop-id={row.loop_id}
                  data-main-status={row.main_status}
                  className={selectedLoopId === row.loop_id ? "is-active" : ""}
                >
                  <td>{row.loop_id}</td>
                  <td title={row.full_title}>{row.short_title}</td>
                  <td>S{row.open_scene}</td>
                  <td>
                    {row.main_label}
                    {row.payoff_type_label ? ` · ${row.payoff_type_label}` : ""}
                  </td>
                  <td>
                    {row.resolve_scene != null ? `S${row.resolve_scene}` : "本章未回收"}
                  </td>
                  <td>{row.has_conflict ? "有" : "无"}</td>
                  <td>
                    <button
                      type="button"
                      className="hook-resolution-locate"
                      data-testid="hook-resolution-locate"
                      onClick={() => locateRow(row)}
                    >
                      查看证据
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
