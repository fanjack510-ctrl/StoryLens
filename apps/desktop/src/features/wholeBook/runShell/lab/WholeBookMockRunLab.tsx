/**
 * WholeBookMockRunLab — isolated Phase 2A Mock Run Lab.
 *
 * MUST NOT be registered in product main navigation / AppShell router.
 * Production start remains disabled; Mock start is a separate control.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  WHOLE_BOOK_ANALYSIS_MODES,
  type WholeBookAnalysisMode,
  type WholeBookModuleKey,
} from "../../contracts/keys";
import type { WholeBookPreflightPageModel } from "../../contracts/preflight";
import {
  PreflightClientError,
  wholeBookPreflightClient,
} from "../../runUx/preflightClient";
import { mapPhase1cPreflightToPageModel } from "../../runUx/preflightMapper";
import {
  FIXTURE_PHASE1C_PREFLIGHT_RESPONSE,
  FIXTURE_PREFLIGHT_ENRICHED,
  FIXTURE_STAGE_PLAN_ROWS,
} from "../../runUx/fixtures/preflightFixtures";
import type {
  PreflightLoadError,
  RunUxTheme,
  StagePlanPreviewRow,
} from "../../runUx/types";
import { WholeBookPreflightView } from "../../runUx/components/WholeBookPreflightView";
import { Button } from "../../../../components/ui/Button";
import {
  createMockWholeBookRunClient,
  type MockWholeBookRunClient,
} from "../client/mockWholeBookRunClient";
import {
  createResultProjectionClient,
} from "../client/resultProjectionClient";
import type { MockWholeBookRunViewDto } from "../client/types";
import { presentMockRunError } from "../client/errors";
import { LAB_UI_LABELS } from "../contracts/actions";
import type { MockProfile } from "../contracts/createRun";
import { useMockRunPolling } from "../polling/useMockRunPolling";
import { MockRunProgressPanel } from "../progress/MockRunProgressPanel";
import {
  createMockRunIdempotencyKey,
  fingerprintModules,
} from "../controls/idempotency";
import { MockLabBanner } from "./MockLabBanner";
import { MockPartialResultsPanel } from "./MockPartialResultsPanel";
import { evaluateLabSurface, type LabAppEnvironment } from "./labVisibility";
import "../../runUx/styles/runUx.css";
import "./styles/mockLab.css";

export type WholeBookMockRunLabProps = {
  bookId?: number;
  useFixtures?: boolean;
  initialTheme?: RunUxTheme;
  appEnvironment?: LabAppEnvironment;
  /** Override WHOLE_BOOK_MOCK_LAB_ENABLED for tests / local lab. */
  labEnabled?: boolean;
  client?: MockWholeBookRunClient;
  resultClient?: ReturnType<typeof createResultProjectionClient>;
  mockProfile?: MockProfile;
  requestedBy?: string;
};

type LabStep = "preflight" | "progress" | "results";

export function WholeBookMockRunLab({
  bookId = 1,
  useFixtures = true,
  initialTheme = "light",
  appEnvironment,
  labEnabled,
  client: clientProp,
  resultClient: resultClientProp,
  mockProfile = "deterministic_minimal",
  requestedBy = "mock-lab-user",
}: WholeBookMockRunLabProps) {
  const surface = evaluateLabSurface({ appEnvironment, labEnabled });
  const client = useMemo(
    () => clientProp ?? createMockWholeBookRunClient(),
    [clientProp],
  );
  const resultClient = useMemo(
    () => resultClientProp ?? createResultProjectionClient(),
    [resultClientProp],
  );

  const [theme, setTheme] = useState<RunUxTheme>(initialTheme);
  const [step, setStep] = useState<LabStep>("preflight");
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
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [confirmEpoch, setConfirmEpoch] = useState(1);
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [runView, setRunView] = useState<MockWholeBookRunViewDto | null>(null);
  const [duplicateNotice, setDuplicateNotice] = useState<string | null>(null);
  const creatingRef = useRef(false);

  const modeDisabledReasons = useMemo(() => {
    const reasons: Partial<Record<WholeBookAnalysisMode, string>> = {};
    for (const m of WHOLE_BOOK_ANALYSIS_MODES) {
      if (!supportedModes.includes(m)) {
        reasons[m] = "supported_modes 来自后端 / Preflight，当前不包含此模式";
      }
    }
    return reasons;
  }, [supportedModes]);

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
        setModel({
          ...mapped.model,
          book: {
            ...mapped.model.book,
            title: FIXTURE_PREFLIGHT_ENRICHED.book.title,
          },
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

  const polling = useMockRunPolling({
    client,
    runId: step === "progress" || step === "results" ? activeRunId : null,
    initialRun: runView,
    enabled: Boolean(activeRunId) && (step === "progress" || step === "results"),
  });

  useEffect(() => {
    if (polling.run) {
      setRunView(polling.run);
    }
  }, [polling.run]);

  const pollingHint = useMemo(() => {
    if (!activeRunId) return null;
    if (polling.lastError) {
      return `轮询暂时失败（连续 ${polling.consecutiveErrors} 次）；不将 Run 标为 failed。`;
    }
    if (!polling.polling) {
      return "轮询已停止（terminal 或已达错误上限）。";
    }
    if (!polling.pageVisible) {
      return `页面不可见：降低轮询频率（约 ${polling.intervalMs ?? "—"}ms）。`;
    }
    return `轮询中 · 间隔约 ${polling.intervalMs ?? "—"}ms（非闪烁提示）。`;
  }, [activeRunId, polling]);

  const startMockRun = async () => {
    if (!surface.enabled || creating || creatingRef.current || !model) return;
    const snapshotId = model.snapshot.snapshot_id;
    if (snapshotId == null) {
      setCreateError("Snapshot 无效：缺少 book_snapshot_id");
      return;
    }
    creatingRef.current = true;
    setCreating(true);
    setCreateError(null);
    setDuplicateNotice(null);
    const configurationFingerprint = `cfg:${bookId}:${mode}:${fingerprintModules(modules)}`;
    const preflightFingerprint = `pf:${bookId}:${snapshotId}:${configurationFingerprint}`;
    const idempotencyKey = createMockRunIdempotencyKey({
      bookId,
      snapshotId,
      analysisMode: mode,
      modulesFingerprint: fingerprintModules(modules),
      configurationFingerprint,
      mockProfile,
      confirmEpoch,
    });
    try {
      const created = await client.create({
        book_id: bookId,
        book_snapshot_id: snapshotId,
        analysis_mode: mode,
        requested_modules: modules,
        configuration_fingerprint: configurationFingerprint,
        idempotency_key: idempotencyKey,
        mock_profile: mockProfile,
        requested_by: requestedBy,
        preflight_fingerprint: preflightFingerprint,
      });
      if (!created.created) {
        setDuplicateNotice(
          `已复用既有 Mock Run #${created.duplicate_of_run_id ?? created.run_id}（created=false）。`,
        );
      }
      const view = await client.get(created.run_id);
      setActiveRunId(created.run_id);
      setRunView(view);
      setStep("progress");
    } catch (err) {
      const presented = presentMockRunError(err);
      setCreateError(`${presented.title}: ${presented.message}`);
      // Do not enter Progress on create failure.
    } finally {
      creatingRef.current = false;
      setCreating(false);
    }
  };

  if (surface.hideEntirely) {
    return null;
  }

  if (!surface.visible) {
    return null;
  }

  if (!surface.enabled) {
    return (
      <div
        className="wb-mock-lab"
        data-testid="whole-book-mock-run-lab"
        data-theme={theme}
        data-lab-enabled="false"
        data-experimental="true"
      >
        <MockLabBanner />
        <div
          className="wb-mock-lab__disabled"
          role="status"
          data-testid="mock-lab-disabled"
        >
          <h1>WholeBook Mock Run Lab</h1>
          <p className="wb-wrap">{surface.disableReason}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="wb-mock-lab wb-run-ux"
      data-testid="whole-book-mock-run-lab"
      data-theme={theme}
      data-lab-enabled="true"
      data-mock="true"
      data-non-production="true"
      data-experimental="true"
      data-step={step}
    >
      <MockLabBanner />

      <div className="wb-run-ux__toolbar" role="banner">
        <strong>WholeBook Mock Run Lab（隔离验证，非产品导航）</strong>
        <div className="wb-run-ux__toolbar-actions">
          <button
            type="button"
            className="wb-linkish"
            data-testid="mock-theme-toggle"
            aria-pressed={theme === "dark"}
            onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
          >
            主题：{theme === "light" ? "浅色" : "深色"}
          </button>
          <button
            type="button"
            className="wb-linkish"
            data-selected={step === "preflight" ? "true" : "false"}
            data-testid="mock-tab-preflight"
            onClick={() => setStep("preflight")}
          >
            Preflight
          </button>
          <button
            type="button"
            className="wb-linkish"
            data-selected={step === "progress" ? "true" : "false"}
            data-testid="mock-tab-progress"
            disabled={!runView}
            title={!runView ? "尚未创建 Mock Run" : "Progress"}
            onClick={() => setStep("progress")}
          >
            Progress
          </button>
          <button
            type="button"
            className="wb-linkish"
            data-selected={step === "results" ? "true" : "false"}
            data-testid="mock-tab-results"
            disabled={!runView?.partial_results_available && !runView?.completed_modules.length}
            title={
              !runView?.partial_results_available &&
              !runView?.completed_modules.length
                ? "尚无部分结果"
                : "Partial Results"
            }
            onClick={() => setStep("results")}
          >
            Partial Results
          </button>
        </div>
      </div>

      {duplicateNotice ? (
        <p role="status" data-testid="duplicate-run-notice" className="wb-mock-lab__feedback">
          {duplicateNotice}
        </p>
      ) : null}

      {step === "preflight" ? (
        <>
          <WholeBookPreflightView
            model={model}
            loading={loading}
            error={error}
            supportedModes={supportedModes}
            stagePlanRows={stageRows}
            modeDisabledReasons={modeDisabledReasons}
            onModeChange={setMode}
            onModulesChange={setModules}
            onRefresh={() => void loadPreflight()}
          />
          <section
            className="wb-mock-lab__section"
            data-testid="mock-start-section"
            aria-labelledby="mock-start-heading"
          >
            <h2 id="mock-start-heading">Mock 验证启动</h2>
            <p className="wb-mock-lab__hint">
              {LAB_UI_LABELS.productionStillDisabled}
              。下方 Mock 按钮与正式启动完全独立，不调用正式 Run Create。
            </p>
            <div className="wb-confirm-actions">
              <Button
                type="button"
                variant="primary"
                disabled={creating || !model}
                title={
                  creating
                    ? "创建中，防重复点击"
                    : LAB_UI_LABELS.mockStartButton
                }
                data-testid="start-mock-whole-book-run"
                aria-busy={creating}
                onClick={() => void startMockRun()}
              >
                {creating
                  ? "创建中…"
                  : LAB_UI_LABELS.mockStartButton}
              </Button>
              <Button
                type="button"
                variant="ghost"
                data-testid="regenerate-idempotency"
                title="生成新的确认 epoch，得到新的 idempotency_key"
                onClick={() => setConfirmEpoch((n) => n + 1)}
              >
                新确认键 (epoch={confirmEpoch})
              </Button>
            </div>
            {createError ? (
              <p
                role="alert"
                className="wb-mock-lab__error wb-wrap"
                data-testid="mock-create-error"
              >
                {createError}
              </p>
            ) : null}
          </section>
        </>
      ) : null}

      {step === "progress" && runView ? (
        <MockRunProgressPanel
          view={runView}
          client={client}
          onViewChange={setRunView}
          pollingHint={pollingHint}
        />
      ) : null}

      {step === "results" && runView ? (
        <MockPartialResultsPanel
          runId={runView.run_id}
          runStatus={runView.status}
          client={resultClient}
        />
      ) : null}
    </div>
  );
}
