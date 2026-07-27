/**
 * Lab-only partial results panel.
 * Integrates read-only Result API; never triggers runs; never auto-canonical.
 */

import { useCallback, useEffect, useState } from "react";
import { Button } from "../../../../components/ui/Button";
import { WholeBookEvidenceDrawer } from "../../review/EvidenceDrawer";
import { StructureMapPrototype } from "../../structureMap";
import {
  FIXTURE_EVIDENCE,
  FIXTURE_STRUCTURE_MAP,
} from "../../contracts/fixtures";
import type { WholeBookEvidenceRefDto } from "../../contracts/evidence";
import type { WholeBookResultEnvelope } from "../../contracts/resultEnvelope";
import type { NarrativeStructureMapProjectionDto } from "../../contracts/structureMap";
import { MODULE_DISPLAY_NAMES } from "../../runUx/labels";
import type { WholeBookModuleKey } from "../../contracts/keys";
import type { resultProjectionClient as ResultClient } from "../client/resultProjectionClient";
import type { WholeBookResultIndexDto } from "../client/types";
import { presentMockRunError } from "../client/errors";
import { LAB_UI_LABELS } from "../contracts/actions";

export type MockPartialResultsPanelProps = {
  runId: number;
  runStatus: string;
  client: Pick<typeof ResultClient, "getIndex" | "getModule">;
  /** Optional structure map projection (read-only). */
  structureMap?: NarrativeStructureMapProjectionDto | null;
  evidence?: WholeBookEvidenceRefDto[];
};

export function MockPartialResultsPanel({
  runId,
  runStatus,
  client,
  structureMap = null,
  evidence = [FIXTURE_EVIDENCE],
}: MockPartialResultsPanelProps) {
  const [index, setIndex] = useState<WholeBookResultIndexDto | null>(null);
  const [selected, setSelected] = useState<WholeBookResultEnvelope | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await client.getIndex(runId);
      setIndex(next);
    } catch (err) {
      const p = presentMockRunError(err);
      setError(`${p.title}: ${p.message}`);
      setIndex(null);
    } finally {
      setLoading(false);
    }
  }, [client, runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const available =
    index?.available_modules?.length && index.available_modules.length > 0;
  if (!available && !loading && !error) {
    return null;
  }

  const openModule = async (moduleKey: string) => {
    setError(null);
    try {
      // Explicit candidate view — never auto-canonical.
      const env = await client.getModule(runId, moduleKey, "candidate");
      setSelected(env);
    } catch (err) {
      const p = presentMockRunError(err);
      setError(`${p.title}: ${p.message}`);
    }
  };

  const projection = structureMap ?? {
    ...FIXTURE_STRUCTURE_MAP,
    source_run_id: runId,
  };

  return (
    <section
      className="wb-mock-lab__section"
      data-testid="mock-partial-results-panel"
      data-run-status={runStatus}
      aria-labelledby="mock-partial-heading"
    >
      <h2 id="mock-partial-heading">部分结果（Lab）</h2>
      <p className="wb-mock-lab__badge" data-testid="mock-badge-results">
        {LAB_UI_LABELS.mockBadge} · candidate · 非正式结果页
      </p>
      <p className="wb-mock-lab__hint">
        Result API 只读，不触发运行。后续 Stage 失败不会隐藏已有结果；cancelled /
        interrupted 仍可查看候选结果。stale ≠ failed。
      </p>

      {loading ? (
        <p role="status" aria-busy="true">
          加载结果索引…
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="wb-mock-lab__error wb-wrap" data-testid="partial-error">
          {error}
        </p>
      ) : null}

      {index ? (
        <ul className="wb-mock-lab__module-cards" data-testid="partial-module-list">
          {index.modules.map((m) => {
            const name =
              MODULE_DISPLAY_NAMES[m.module_key as WholeBookModuleKey] ??
              m.module_key;
            const readable =
              m.module_status === "completed" ||
              m.module_status === "partial" ||
              index.available_modules.includes(m.module_key);
            if (!readable && m.module_status === "failed") {
              // Failed modules still listed but marked — do not hide completed siblings.
            }
            return (
              <li
                key={m.module_key}
                className="wb-mock-lab__module-card"
                data-testid={`partial-module-${m.module_key}`}
                data-status={m.module_status}
                data-partial={m.partial ? "true" : "false"}
                data-stale={m.stale ? "true" : "false"}
                data-candidate="true"
              >
                <div>
                  <strong>{name}</strong>
                  <span className="wb-mock-lab__meta">
                    {" "}
                    · {m.module_status}
                    {m.partial ? " · partial" : ""}
                    {m.module_status === "completed" ? " · completed" : ""}
                    {" · candidate"}
                    {m.stale ? " · stale" : ""}
                  </span>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={!readable}
                  title={!readable ? "模块尚不可读" : "打开候选结果卡片"}
                  data-testid={`open-module-${m.module_key}`}
                  onClick={() => void openModule(m.module_key)}
                >
                  打开候选结果
                </Button>
              </li>
            );
          })}
        </ul>
      ) : null}

      {selected ? (
        <article
          className="wb-mock-lab__envelope"
          data-testid="partial-envelope-card"
          data-partial={selected.partial ? "true" : "false"}
          data-stale={selected.stale ? "true" : "false"}
          data-candidate="true"
          data-mock="true"
        >
          <h3>
            {MODULE_DISPLAY_NAMES[selected.module_key] ?? selected.module_key}
          </h3>
          <p>
            status={selected.module_status}
            {selected.partial ? " · partial" : ""}
            {selected.module_status === "completed" ? " · completed" : ""}
            {" · candidate · mock/non-production"}
            {selected.stale ? " · stale（≠ failed）" : ""}
          </p>
          <p className="wb-wrap">
            warnings: {selected.warnings.join("；") || "无"}
          </p>
          <pre className="wb-code-block" data-testid="envelope-payload-preview">
            {JSON.stringify(selected.payload, null, 2).slice(0, 1200)}
          </pre>
        </article>
      ) : null}

      <div className="wb-mock-lab__result-entries">
        <Button
          type="button"
          variant="secondary"
          data-testid="open-evidence-drawer"
          onClick={() => setEvidenceOpen(true)}
        >
          Evidence（按需）
        </Button>
        <Button
          type="button"
          variant="secondary"
          data-testid="open-structure-map"
          onClick={() => setMapOpen(true)}
        >
          Structure Map（只读 Projection）
        </Button>
      </div>

      <WholeBookEvidenceDrawer
        open={evidenceOpen}
        title="Mock Lab Evidence"
        evidence={evidence}
        onClose={() => setEvidenceOpen(false)}
      />

      {mapOpen ? (
        <div
          className="wb-mock-lab__map"
          data-testid="mock-structure-map"
          role="region"
          aria-label="Structure Map 只读投影"
        >
          <div className="wb-mock-lab__map-toolbar">
            <Button
              type="button"
              variant="ghost"
              data-testid="close-structure-map"
              onClick={() => setMapOpen(false)}
            >
              关闭 Structure Map
            </Button>
          </div>
          <StructureMapPrototype projection={projection} />
        </div>
      ) : null}
    </section>
  );
}
