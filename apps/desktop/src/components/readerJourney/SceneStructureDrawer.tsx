import type { SceneResultItem } from "../../types";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";

type Props = {
  open: boolean;
  onClose: () => void;
  scenes: SceneResultItem[];
  visualization: ReaderJourneyVisualization;
  activeSceneOrdinal: number | null;
  onSelectScene: (sceneId: number) => void;
};

function fieldSummary(field?: { summary: string }): string {
  if (!field?.summary?.trim()) return "无";
  return field.summary.trim();
}

export function SceneStructureDrawer({
  open,
  onClose,
  scenes,
  visualization,
  activeSceneOrdinal,
  onSelectScene,
}: Props) {
  if (!open) return null;

  const nodeByOrdinal = new Map(
    visualization.scene_nodes.map((node) => [node.scene_ordinal, node]),
  );

  return (
    <div className="scene-structure-drawer-overlay" data-testid="scene-structure-drawer">
      <div className="scene-structure-drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <aside className="scene-structure-drawer-panel" role="dialog" aria-modal="true">
        <header className="scene-structure-drawer-head">
          <h3>章节结构</h3>
          <button type="button" onClick={onClose}>
            关闭
          </button>
        </header>
        <div className="scene-structure-drawer-list">
          {scenes.map((item) => {
            const s = item.scene;
            const node = nodeByOrdinal.get(s.ordinal);
            const goal = fieldSummary(item.analysis_artifact?.analysis.goal);
            return (
              <button
                key={s.id}
                type="button"
                data-testid={`drawer-scene-item-${s.ordinal}`}
                className={activeSceneOrdinal === s.ordinal ? "selected" : ""}
                onClick={() => {
                  onSelectScene(s.id);
                  onClose();
                }}
              >
                <span className="scene-line">
                  <b>Scene {String(s.ordinal).padStart(2, "0")}</b>
                  {node && <span className={`role-tag role-${node.role}`}>{node.role}</span>}
                </span>
                <small>
                  {s.start_paragraph_id} → {s.end_paragraph_id}
                </small>
                <small className="scene-goal">{goal}</small>
              </button>
            );
          })}
        </div>
      </aside>
    </div>
  );
}
