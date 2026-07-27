/**
 * Shared Vitest helpers for Reader Journey UI contract (CHG-20260723-006).
 * Presentation tests only — no algorithm changes.
 */
import { fireEvent, screen } from "@testing-library/react";
import { expect } from "vitest";

/** Removed with hierarchy simplification — assert absence in updated tests. */
export function expectRemovedHierarchyChrome() {
  expect(screen.queryByTestId("journey-more-chart-settings")).not.toBeInTheDocument();
  expect(screen.queryByTestId("journey-summary-cards")).not.toBeInTheDocument();
  expect(screen.queryByTestId("journey-curve-legend")).not.toBeInTheDocument();
  expect(screen.queryByTestId("journey-marker-toggle")).not.toBeInTheDocument();
  expect(screen.queryByTestId("journey-analysis-title")).not.toBeInTheDocument();
  expect(screen.queryByText("更多操作")).not.toBeInTheDocument();
}

/** PNG export is off the removed 更多操作 menu — hidden compatibility trigger on workspace. */
export function getJourneyExportButton() {
  return screen.getByTestId("journey-export-png");
}

export function triggerJourneyExportPng() {
  const btn = getJourneyExportButton();
  fireEvent.click(btn);
  return btn;
}

/** @deprecated Use triggerJourneyExportPng — kept for legacy test call sites. */
export function openExportMenu() {
  return triggerJourneyExportPng();
}

/** Visible journey title for export / ordinary audits after header simplification. */
export function expectJourneyTitleVisible() {
  expect(screen.getByTestId("journey-export-title")).toHaveTextContent("阅读旅程");
}
