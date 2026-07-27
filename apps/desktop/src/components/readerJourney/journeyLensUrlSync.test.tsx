import { describe, expect, it, afterEach } from "vitest";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import { render, screen, fireEvent, act, cleanup } from "@testing-library/react";
import {
  lensIdFromMetric,
  metricForLens,
  parseLensParam,
} from "./readerJourneyLensExplanation";

afterEach(() => cleanup());

function LensUrlProbe() {
  const [params, setParams] = useSearchParams();
  const lens = parseLensParam(params.get("lens")) ?? lensIdFromMetric(params.get("metric"));
  return (
    <div>
      <span data-testid="current-lens">{lens}</span>
      <span data-testid="current-metric">{params.get("metric")}</span>
      <span data-testid="current-loop">{params.get("loop") || ""}</span>
      <button
        type="button"
        data-testid="set-hook-lens"
        onClick={() => {
          const next = new URLSearchParams(params);
          next.set("lens", "hook_payoff");
          next.set("metric", metricForLens("hook_payoff"));
          setParams(next, { replace: true });
        }}
      >
        hook
      </button>
      <button
        type="button"
        data-testid="set-loop"
        onClick={() => {
          const next = new URLSearchParams(params);
          next.set("loop", "L99");
          setParams(next, { replace: true });
        }}
      >
        loop
      </button>
      <button
        type="button"
        data-testid="clear-bad-lens"
        onClick={() => {
          const next = new URLSearchParams(params);
          next.set("lens", "invalid");
          setParams(next, { replace: true });
        }}
      >
        bad
      </button>
    </div>
  );
}

describe("lens/loop URL sync helpers", () => {
  it("updates metric when lens changes and restores from URL", () => {
    render(
      <MemoryRouter initialEntries={["/?metric=engagement"]}>
        <LensUrlProbe />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("current-lens").textContent).toBe("composite");
    fireEvent.click(screen.getByTestId("set-hook-lens"));
    expect(screen.getByTestId("current-lens").textContent).toBe("hook_payoff");
    expect(screen.getByTestId("current-metric").textContent).toBe("hook");
  });

  it("keeps loop param and falls back illegal lens via parse", () => {
    render(
      <MemoryRouter initialEntries={["/?lens=hook_payoff&loop=L1"]}>
        <LensUrlProbe />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("current-loop").textContent).toBe("L1");
    fireEvent.click(screen.getByTestId("set-loop"));
    expect(screen.getByTestId("current-loop").textContent).toBe("L99");
    act(() => {
      fireEvent.click(screen.getByTestId("clear-bad-lens"));
    });
    expect(parseLensParam("invalid")).toBeNull();
  });
});
