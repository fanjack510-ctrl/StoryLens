/**
 * Read-only Result Projection client for Lab partial results.
 * Uses Phase 1D Result API — never triggers runs.
 */

import { api } from "../../../../services/apiClient";
import type { WholeBookResultEnvelope } from "../../contracts/resultEnvelope";
import { assertResultEnvelope } from "../../contracts/guards";
import { assertNoSensitiveKeys, assertResultIndex } from "./dtoGuards";
import { toMockRunClientError } from "./errors";
import {
  RESULT_INDEX_PATH,
  RESULT_MODULE_PATH,
  type WholeBookResultIndexDto,
} from "./types";

export type ResultProjectionClientDeps = {
  request?: typeof api;
  onRequestPath?: (method: string, path: string) => void;
};

export function createResultProjectionClient(
  deps: ResultProjectionClientDeps = {},
) {
  const request = deps.request ?? api;

  return {
    async getIndex(runId: number): Promise<WholeBookResultIndexDto> {
      const path = RESULT_INDEX_PATH.replace("{run_id}", String(runId));
      deps.onRequestPath?.("GET", path);
      try {
        const raw = await request<unknown>(path);
        return assertResultIndex(raw);
      } catch (error) {
        throw toMockRunClientError(error);
      }
    },

    async getModule(
      runId: number,
      moduleKey: string,
      view: "canonical" | "candidate" = "candidate",
    ): Promise<WholeBookResultEnvelope> {
      // Lab always prefers candidate; never auto-canonical.
      const path =
        RESULT_MODULE_PATH.replace("{run_id}", String(runId)).replace(
          "{module_key}",
          encodeURIComponent(moduleKey),
        ) + `?view=${view}`;
      deps.onRequestPath?.("GET", path);
      try {
        const raw = await request<unknown>(path);
        if (!raw || typeof raw !== "object") {
          throw toMockRunClientError(new Error("invalid envelope"));
        }
        assertNoSensitiveKeys(raw as Record<string, unknown>);
        const env = raw as WholeBookResultEnvelope;
        assertResultEnvelope(env);
        return env;
      } catch (error) {
        throw toMockRunClientError(error);
      }
    },
  };
}

export const resultProjectionClient = createResultProjectionClient();
