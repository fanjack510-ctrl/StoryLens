import { useCallback, useEffect, useMemo, useState } from "react";
import {
  WHOLE_BOOK_ANALYSIS_MODES,
  type WholeBookAnalysisMode,
  type WholeBookModuleKey,
} from "../../contracts/keys";
import type { WholeBookPreflightPageModel } from "../../contracts/preflight";
import type { WholeBookRunViewState } from "../../contracts/runView";
import {
  PreflightClientError,
  wholeBookPreflightClient,
} from "../preflightClient";
import { mapPhase1cPreflightToPageModel } from "../preflightMapper";
import {
  FIXTURE_PHASE1C_PREFLIGHT_RESPONSE,
  FIXTURE_PREFLIGHT_ENRICHED,
  FIXTURE_STAGE_PLAN_ROWS,
} from "../fixtures/preflightFixtures";
import { FIXTURE_RUN_RUNNING, RUN_VIEW_FIXTURES } from "../fixtures/runViewFixtures";
import type {
  PreflightLoadError,
  RunUxTheme,
  StagePlanPreviewRow,
} from "../types";
import { WholeBookPreflightView } from "../components/WholeBookPreflightView";
import { WholeBookRunProgressView } from "../components/WholeBookRunProgressView";
import "../styles/runUx.css";

export type WholeBookRunUxLabPageProps = {
  bookId?: number;
  /** Use fixtures only — default for isolated prototype (no live backend required). */
  useFixtures?: boolean;
  initialTheme?: RunUxTheme;
  initialRunFixture?: keyof typeof RUN_VIEW_FIXTURES;
};

/**
 * Isolated lab page — MUST NOT be registered in product main navigation.
 * Optional deep-link route fixture may mount this for experiments.
 */
export function WholeBookRunUxLabPage({
  bookId = 1,
  useFixtures = true,
  initialTheme = "light",
  initialRunFixture = "running",
}: WholeBookRunUxLabPageProps) {
  const [theme, setTheme] = useState<RunUxTheme>(initialTheme);
  const [tab, setTab] = useState<"preflight" | "progress">("preflight");
  const [mode, setMode] = useState<WholeBookAnalysisMode>("whole_book_native");
  const [modules, setModules] = useState<WholeBookModuleKey[]>([
    "book_overview",
    "structure_stages",
  ]);
  const [model, setModel] = useState<WholeBookPreflightPageModel | null>(
    useFixtures ? FIXTURE_PREFLIGHT_ENRICHED : null,
  );
  const [stageRows, setStageRows] = useState<StagePlanPreviewRow[]>(
    FIXTURE_STAGE_PLAN_ROWS,
  );
  const [supportedModes, setSupportedModes] = useState<WholeBookAnalysisMode[]>([
    ...WHOLE_BOOK_ANALYSIS_MODES,
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<PreflightLoadError | null>(null);
  const [runView, setRunView] = useState<WholeBookRunViewState>(
    RUN_VIEW_FIXTURES[initialRunFixture] ?? FIXTURE_RUN_RUNNING,
  );

  const modeDisabledReasons = useMemo(() => {
    const reasons: Partial<Record<WholeBookAnalysisMode, string>> = {};
    for (const m of WHOLE_BOOK_ANALYSIS_MODES) {
      if (!supportedModes.includes(m)) {
        reasons[m] = "supported_modes 来自后端 / Preflight，当前不包含此模式";
      }
    }
    if (model?.blocking_reasons.includes("CAPABILITY_MODE_NOT_SUPPORTED")) {
      reasons[mode] =
        model.capability.message || "CAPABILITY_MODE_NOT_SUPPORTED";
    }
    return reasons;
  }, [supportedModes, model, mode]);

  const loadPreflight = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (useFixtures) {
        const mapped = mapPhase1cPreflightToPageModel(
          {
            ...FIXTURE_PHASE1C_PREFLIGHT_RESPONSE,
            analysis_mode: mode,
            requested_mode: mode,
            requested_modules: modules,
            notes: {
              ...FIXTURE_PHASE1C_PREFLIGHT_RESPONSE.notes,
              requested_modules: modules,
            },
          },
          modules,
        );
        // Keep enriched stage metadata for UX demo.
        setModel({
          ...mapped.model,
          book: { ...mapped.model.book, title: FIXTURE_PREFLIGHT_ENRICHED.book.title },
          source_coverage:
            mode === "whole_book_enhanced"
              ? FIXTURE_PREFLIGHT_ENRICHED.source_coverage
              : mapped.model.source_coverage,
          force_start_allowed: false,
          backend_run_creation_enabled: mapped.model.backend_run_creation_enabled,
          client_run_creation_enabled: mapped.model.client_run_creation_enabled,
          effective_run_creation_enabled: false,
          run_creation_enabled: false,
        });
        setStageRows(
          mapped.stage_plan_rows.length
            ? mapped.stage_plan_rows
            : FIXTURE_STAGE_PLAN_ROWS,
        );
        setSupportedModes(mapped.supported_modes);
        return;
      }

      const result = await wholeBookPreflightClient.fetch(bookId, {
        analysis_mode: mode,
        requested_modules: modules,
      });
      setModel(result.model);
      setStageRows(result.stage_plan_rows);
      setSupportedModes(result.supported_modes);
    } catch (err) {
      const clientError =
        err instanceof PreflightClientError
          ? err
          : new PreflightClientError(
              err instanceof Error ? err.message : "Preflight 失败",
              "NETWORK",
              err,
            );
      setError(clientError.toLoadError());
      setModel(wholeBookPreflightClient.failClosed(bookId, clientError));
      setStageRows([]);
      setSupportedModes([]);
    } finally {
      setLoading(false);
    }
  }, [bookId, mode, modules, useFixtures]);

  useEffect(() => {
    void loadPreflight();
  }, [loadPreflight]);

  const onModeChange = (next: WholeBookAnalysisMode) => {
    setMode(next);
  };

  const onModulesChange = (next: WholeBookModuleKey[]) => {
    setModules(next);
  };

  return (
    <div
      className="wb-run-ux"
      data-testid="whole-book-run-ux-lab"
      data-theme={theme}
      data-experimental="true"
    >
      <div className="wb-run-ux__toolbar" role="banner">
        <strong>Whole Book Run UX Lab（实验入口，非产品导航）</strong>
        <div className="wb-run-ux__toolbar-actions">
          <button
            type="button"
            className="wb-linkish"
            data-testid="theme-toggle"
            aria-pressed={theme === "dark"}
            onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
          >
            主题：{theme === "light" ? "浅色" : "深色"}
          </button>
          <button
            type="button"
            className="wb-linkish"
            data-selected={tab === "preflight" ? "true" : "false"}
            data-testid="tab-preflight"
            onClick={() => setTab("preflight")}
          >
            Preflight
          </button>
          <button
            type="button"
            className="wb-linkish"
            data-selected={tab === "progress" ? "true" : "false"}
            data-testid="tab-progress"
            onClick={() => setTab("progress")}
          >
            Run Progress
          </button>
          <label className="wb-run-ux__fixture-select">
            Progress Fixture
            <select
              data-testid="run-fixture-select"
              value={Object.entries(RUN_VIEW_FIXTURES).find(
                ([, v]) => v.status === runView.status && v.run_id === runView.run_id,
              )?.[0] ?? initialRunFixture}
              onChange={(e) => {
                const key = e.target.value as keyof typeof RUN_VIEW_FIXTURES;
                setRunView(RUN_VIEW_FIXTURES[key]);
              }}
            >
              {Object.keys(RUN_VIEW_FIXTURES).map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {tab === "preflight" ? (
        <WholeBookPreflightView
          model={model}
          loading={loading}
          error={error}
          supportedModes={supportedModes}
          stagePlanRows={stageRows}
          modeDisabledReasons={modeDisabledReasons}
          onModeChange={onModeChange}
          onModulesChange={onModulesChange}
          onRefresh={() => void loadPreflight()}
          onBackToBook={() => undefined}
          onViewPreview={() => undefined}
          onViewSnapshot={() => undefined}
        />
      ) : (
        <WholeBookRunProgressView
          view={runView}
          onViewChange={setRunView}
        />
      )}
    </div>
  );
}
