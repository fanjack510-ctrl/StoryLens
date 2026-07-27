import {
  MODULE_STAGE_DEPENDENCIES,
  WHOLE_BOOK_MODULE_KEYS,
  type WholeBookModuleKey,
} from "../../contracts/keys";
import { resolveModulesWithDependencies } from "../../contracts/guards";
import { MODULE_DISPLAY_NAMES } from "../labels";

export type WholeBookModuleSelectorProps = {
  requestedModules: readonly WholeBookModuleKey[];
  resolvedModules: readonly WholeBookModuleKey[];
  autoFillNotes?: readonly string[];
  onChange: (requested: WholeBookModuleKey[]) => void;
};

/**
 * Module ≠ Stage. Dependency graph comes from shared MODULE_STAGE_DEPENDENCIES /
 * resolveModulesWithDependencies — not a second in-component graph.
 */
export function WholeBookModuleSelector({
  requestedModules,
  resolvedModules,
  autoFillNotes = [],
  onChange,
}: WholeBookModuleSelectorProps) {
  const requested = new Set(requestedModules);
  const resolved = new Set(resolvedModules);
  const autoFilledModules = [...resolved].filter((m) => !requested.has(m));

  const { stages, notes } = resolveModulesWithDependencies(
    requestedModules.length > 0
      ? [...requestedModules]
      : [...WHOLE_BOOK_MODULE_KEYS],
  );

  const toggle = (key: WholeBookModuleKey) => {
    // Auto-filled required dependency modules cannot be unchecked directly.
    if (autoFilledModules.includes(key) && !requested.has(key)) {
      return;
    }
    const next = new Set(requestedModules);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onChange([...WHOLE_BOOK_MODULE_KEYS].filter((k) => next.has(k)));
  };

  return (
    <section
      className="wb-run-ux__section"
      data-testid="whole-book-module-selector"
      aria-labelledby="wb-module-heading"
    >
      <h2 id="wb-module-heading">分析模块</h2>
      <p className="wb-run-ux__hint">
        模块与 Stage 分离。勾选模块后系统展示 resolved_modules，并自动补齐必要依赖阶段。
      </p>
      <ul className="wb-module-list" role="group" aria-label="模块列表">
        {WHOLE_BOOK_MODULE_KEYS.map((key) => {
          const checked = requested.has(key) || resolved.has(key);
          const isAuto = autoFilledModules.includes(key);
          const isRequested = requested.has(key);
          const deps = MODULE_STAGE_DEPENDENCIES[key];
          const isDiagnostics = key === "diagnostics";
          const locked = isAuto && !isRequested;
          return (
            <li
              key={key}
              className="wb-module-item"
              data-testid={`module-item-${key}`}
              data-auto-filled={isAuto ? "true" : "false"}
              data-required-locked={locked ? "true" : "false"}
            >
              <label className="wb-module-item__label">
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={locked}
                  aria-disabled={locked || undefined}
                  title={
                    locked
                      ? "自动补齐的必需依赖，不可取消"
                      : MODULE_DISPLAY_NAMES[key]
                  }
                  data-testid={`module-check-${key}`}
                  onChange={() => toggle(key)}
                />
                <span className="wb-module-item__name">
                  {MODULE_DISPLAY_NAMES[key]}
                </span>
                {isAuto ? (
                  <span className="wb-chip wb-chip--auto" aria-label="自动补齐依赖">
                    自动依赖
                  </span>
                ) : null}
                {isDiagnostics ? (
                  <span className="wb-chip wb-chip--warn" aria-label="依赖较多">
                    依赖较多
                  </span>
                ) : null}
              </label>
              <p className="wb-module-item__deps">
                依赖阶段（共享契约）：{deps.join(" → ")}
              </p>
              <span className="wb-visually-hidden">模块键 {key}</span>
            </li>
          );
        })}
      </ul>

      <div className="wb-resolved" data-testid="resolved-modules" role="status">
        <strong>resolved_modules</strong>
        <p>{resolvedModules.length ? resolvedModules.join(", ") : "（空）"}</p>
      </div>

      <div className="wb-resolved" data-testid="resolved-stages" role="status">
        <strong>将执行的依赖阶段（非模块）</strong>
        <p>{stages.join(", ")}</p>
      </div>

      {(autoFillNotes.length > 0 || notes.length > 0) && (
        <div className="wb-autofill-notes" data-testid="autofill-notes">
          <strong>依赖说明</strong>
          <ul>
            {(autoFillNotes.length > 0 ? autoFillNotes : notes).map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
          {requested.has("diagnostics") || resolved.has("diagnostics") ? (
            <p className="wb-run-ux__warn" data-testid="diagnostics-dependency-hint">
              diagnostics 依赖结构 / 故事线 / 人物 / 伏笔 / 因果与证据校验等多个阶段，成本较高。
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}
