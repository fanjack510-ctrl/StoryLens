import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, it, expect, vi } from "vitest";
import { App } from "./App";

vi.stubGlobal(
  "fetch",
  vi.fn(
    async (url: string) =>
      new Response(
        JSON.stringify(
          String(url).includes("/health")
            ? { status: "ok", database: "ok", default_provider: "none" }
            : String(url).includes("/books")
              ? []
              : String(url).includes("dashboard")
                ? {
                    books: 0,
                    chapters: 0,
                    paragraphs: 0,
                    scenes: 0,
                    successful_runs: 0,
                    failed_runs: 0,
                    cloud_invocations: 0,
                    local_invocations: 0,
                  }
                : [],
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  ),
);

describe("App", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders navigation and redirects home to library", async () => {
    render(<App />);
    expect(screen.getByTestId("nav-library")).toBeInTheDocument();
    expect(await screen.findByTestId("library-page")).toBeInTheDocument();
  });
});
