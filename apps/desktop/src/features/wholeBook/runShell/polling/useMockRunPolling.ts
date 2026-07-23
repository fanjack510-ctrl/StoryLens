/**
 * React hook wrapping MockRunPollingController.
 */

import { useEffect, useRef, useState } from "react";
import type { MockWholeBookRunClient } from "../client/mockWholeBookRunClient";
import type { MockWholeBookRunViewDto } from "../client/types";
import type { MockRunPollingPolicy } from "../contracts/polling";
import {
  MockRunPollingController,
  type PollingSnapshot,
} from "./mockRunPollingController";

export type UseMockRunPollingOptions = {
  client: Pick<MockWholeBookRunClient, "get">;
  runId: number | null;
  initialRun?: MockWholeBookRunViewDto | null;
  policy?: MockRunPollingPolicy;
  enabled?: boolean;
};

export function useMockRunPolling(
  options: UseMockRunPollingOptions,
): PollingSnapshot {
  const { client, runId, initialRun = null, policy, enabled = true } = options;
  const [snap, setSnap] = useState<PollingSnapshot>({
    run: initialRun,
    lastSuccessAt: null,
    consecutiveErrors: 0,
    polling: false,
    pageVisible: true,
    lastError: null,
    intervalMs: null,
  });
  const controllerRef = useRef<MockRunPollingController | null>(null);

  useEffect(() => {
    const controller = new MockRunPollingController({
      client,
      policy,
      onSnapshot: setSnap,
    });
    controllerRef.current = controller;
    return () => {
      controller.dispose();
      controllerRef.current = null;
    };
  }, [client, policy]);

  useEffect(() => {
    const controller = controllerRef.current;
    if (!controller) return;
    if (!enabled || runId == null) {
      controller.stop();
      return;
    }
    controller.start(runId, initialRun ?? null);
    return () => {
      controller.stop();
    };
    // initialRun only seeds the first start for a given runId
    // eslint-disable-next-line react-hooks/exhaustive-deps -- avoid restart on every poll update
  }, [enabled, runId, client]);

  return snap;
}

export { MockRunPollingController } from "./mockRunPollingController";
export type { PollingSnapshot } from "./mockRunPollingController";
