/**
 * Isolated Lab route constant — NOT registered in product AppShell router.
 * Integration may later mount under a hidden /dev path.
 */

import type { RouteObject } from "react-router-dom";
import { WholeBookMockRunLab } from "./WholeBookMockRunLab";

export const WHOLE_BOOK_MOCK_RUN_LAB_PATH = "/dev/whole-book-mock-run-lab";

/** Fixture only — do not import into apps/desktop/src/app/router.tsx. */
export const wholeBookMockRunLabIsolatedRoute: RouteObject = {
  path: WHOLE_BOOK_MOCK_RUN_LAB_PATH,
  element: <WholeBookMockRunLab labEnabled useFixtures />,
};

export function createWholeBookMockRunLabIsolatedRoutes(): RouteObject[] {
  return [wholeBookMockRunLabIsolatedRoute];
}
