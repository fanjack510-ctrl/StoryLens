/**
 * Lab visibility helpers — production hidden; disabled shows reason.
 */

import { WHOLE_BOOK_MOCK_LAB_ENABLED } from "../contracts/mockLab";
import { MOCK_RUN_ERROR_MESSAGES } from "../contracts/errors";
import { isMockLabUiVisible } from "../contracts/guards";
import { MOCK_RUN_ERROR_UI_LABELS } from "../client/errors";

export type LabAppEnvironment = "development" | "test" | "production" | string;

export function resolveAppEnvironment(
  override?: LabAppEnvironment,
): LabAppEnvironment {
  if (override) return override;
  if (typeof import.meta !== "undefined" && import.meta.env?.MODE === "test") {
    return "test";
  }
  if (typeof import.meta !== "undefined" && import.meta.env?.DEV) {
    return "development";
  }
  if (typeof import.meta !== "undefined" && import.meta.env?.PROD) {
    return "production";
  }
  return "development";
}

export function evaluateLabSurface(params: {
  appEnvironment?: LabAppEnvironment;
  labEnabled?: boolean;
}): {
  visible: boolean;
  enabled: boolean;
  hideEntirely: boolean;
  disableReason: string | null;
} {
  const appEnvironment = resolveAppEnvironment(params.appEnvironment);
  const labEnabled = params.labEnabled ?? WHOLE_BOOK_MOCK_LAB_ENABLED;

  if (appEnvironment === "production") {
    return {
      visible: false,
      enabled: false,
      hideEntirely: true,
      disableReason: MOCK_RUN_ERROR_UI_LABELS.MOCK_LAB_ENVIRONMENT_NOT_ALLOWED,
    };
  }

  const visible = isMockLabUiVisible({ appEnvironment, labEnabled: true });
  // Show surface in dev/test even when lab flag is off — with disabled reason.
  if (!labEnabled) {
    return {
      visible: true,
      enabled: false,
      hideEntirely: false,
      disableReason: `${MOCK_RUN_ERROR_UI_LABELS.MOCK_LAB_DISABLED} — ${MOCK_RUN_ERROR_MESSAGES.MOCK_LAB_DISABLED}`,
    };
  }

  return {
    visible,
    enabled: true,
    hideEntirely: false,
    disableReason: null,
  };
}
