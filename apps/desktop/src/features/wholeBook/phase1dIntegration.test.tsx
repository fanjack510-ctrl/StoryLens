/**
 * Phase 1D Integration — frontend contract / isolation smoke tests.
 */
import { describe, expect, it } from "vitest";
import {
  PRODUCT_MODULE_STAGE_DEPENDENCIES,
  MODULE_STAGE_DEPENDENCIES,
  WHOLE_BOOK_MODULE_KEYS,
  resolveModulesWithDependencies,
  assertPreflightGuard,
} from "./contracts";
import { FIXTURE_PREFLIGHT } from "./contracts/fixtures";
import {
  mapPhase1cPreflightToPageModel,
  failClosedPreflightModel,
} from "./runUx/preflightMapper";
import { RUN_CREATE_ENABLED_IN_CLIENT } from "./runUx/constants";
import { FIXTURE_PHASE1C_PREFLIGHT_RESPONSE } from "./runUx/fixtures/preflightFixtures";
import { WHOLE_BOOK_RUN_UX_LAB_PATH } from "./runUx";
import * as review from "./review";
import * as structureMap from "./structureMap";

describe("phase1d integration frontend", () => {
  it("exposes isolated feature barrels without product nav coupling", () => {
    expect(WHOLE_BOOK_RUN_UX_LAB_PATH).toContain("whole-book-run-ux");
    expect(review.WholeBookEvidenceDrawer).toBeTypeOf("function");
    expect(review.ConflictCenterPrototype).toBeTypeOf("function");
    expect(structureMap.StructureMapPrototype).toBeTypeOf("function");
    expect(RUN_CREATE_ENABLED_IN_CLIENT).toBe(false);
  });

  it("maps transport DTO preserving backend/client/effective run creation", () => {
    const mapped = mapPhase1cPreflightToPageModel(
      FIXTURE_PHASE1C_PREFLIGHT_RESPONSE,
    );
    expect(mapped.model.backend_run_creation_enabled).toBe(false);
    expect(mapped.model.client_run_creation_enabled).toBe(false);
    expect(mapped.model.effective_run_creation_enabled).toBe(false);
    expect(mapped.model.run_creation_enabled).toBe(false);
    assertPreflightGuard(mapped.model);
  });

  it("keeps effective false when transport claims backend true", () => {
    const mapped = mapPhase1cPreflightToPageModel({
      ...FIXTURE_PHASE1C_PREFLIGHT_RESPONSE,
      run_creation_enabled: true,
    });
    expect(mapped.model.backend_run_creation_enabled).toBe(true);
    expect(mapped.model.client_run_creation_enabled).toBe(false);
    expect(mapped.model.effective_run_creation_enabled).toBe(false);
    expect(mapped.model.warnings).toContain("CLIENT_RUN_CREATION_DISABLED");
  });

  it("fail-closes transport errors", () => {
    const closed = failClosedPreflightModel(1, "offline");
    expect(closed.effective_run_creation_enabled).toBe(false);
    expect(closed.capability.allowed).toBe(false);
  });

  it("uses PRODUCT_MODULE_STAGE_DEPENDENCIES (no third FE engine table)", () => {
    expect(PRODUCT_MODULE_STAGE_DEPENDENCIES).toBe(MODULE_STAGE_DEPENDENCIES);
    expect(Object.keys(PRODUCT_MODULE_STAGE_DEPENDENCIES).sort()).toEqual(
      [...WHOLE_BOOK_MODULE_KEYS].sort(),
    );
    const resolved = resolveModulesWithDependencies(["characters"]);
    expect(resolved.stages).toContain("resolve_entities");
    expect(resolved.stages).toContain("analyze_characters");
  });

  it("fixture page model passes guard", () => {
    assertPreflightGuard(FIXTURE_PREFLIGHT);
    expect(FIXTURE_PREFLIGHT.force_start_allowed).toBe(false);
  });

  it("rejects unknown module in mapper", () => {
    expect(() =>
      mapPhase1cPreflightToPageModel({
        ...FIXTURE_PHASE1C_PREFLIGHT_RESPONSE,
        requested_modules: ["not_a_module"],
        resolved_modules: [],
        notes: {},
      }),
    ).toThrow(/UNKNOWN_MODULE/);
  });
});
