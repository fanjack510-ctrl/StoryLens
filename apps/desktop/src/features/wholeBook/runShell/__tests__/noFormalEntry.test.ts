import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { WHOLE_BOOK_MOCK_RUN_LAB_PATH } from "../lab/isolatedRoute";
import { FORMAL_RUN_CREATE_PATH, LAB_API_BASE } from "../client/types";
import { RUN_CREATE_ENABLED_IN_CLIENT } from "../../runUx/constants";

const routerSource = readFileSync(
  join(process.cwd(), "src/app/router.tsx"),
  "utf8",
);

describe("No formal entry / no product router wiring", () => {
  it("product router does not include mock lab path", () => {
    expect(routerSource).not.toContain(WHOLE_BOOK_MOCK_RUN_LAB_PATH);
    expect(routerSource).not.toContain("WholeBookMockRunLab");
    expect(routerSource).not.toContain("whole-book-mock-run-lab");
  });

  it("formal create remains disabled and distinct from lab API", () => {
    expect(RUN_CREATE_ENABLED_IN_CLIENT).toBe(false);
    expect(FORMAL_RUN_CREATE_PATH).toBe(
      "/api/v1/books/{book_id}/whole-book-runs",
    );
    expect(LAB_API_BASE).toBe("/api/v1/labs/whole-book-runs");
    expect(LAB_API_BASE).not.toEqual(
      FORMAL_RUN_CREATE_PATH.replace("{book_id}", "1"),
    );
  });
});
