/**
 * Isolated route fixture — not registered in product AppShell navigation.
 * Integration may later mount under a hidden /dev path.
 */

import type { RouteObject } from "react-router-dom";
import { WholeBookRunUxLabPage } from "../pages/WholeBookRunUxLabPage";

export const WHOLE_BOOK_RUN_UX_LAB_PATH = "/dev/whole-book-run-ux";

export const wholeBookRunUxIsolatedRoute: RouteObject = {
  path: WHOLE_BOOK_RUN_UX_LAB_PATH,
  element: <WholeBookRunUxLabPage useFixtures />,
};

export function createWholeBookRunUxIsolatedRoutes(): RouteObject[] {
  return [wholeBookRunUxIsolatedRoute];
}
