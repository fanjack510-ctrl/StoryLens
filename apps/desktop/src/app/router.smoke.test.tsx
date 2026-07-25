import { describe, expect, it } from "vitest";
import { router } from "./router";

describe("app router bootstrap", () => {
  it("imports createBrowserRouter without ReferenceError", () => {
    expect(router).toBeTruthy();
    const paths = router.routes.flatMap((route) => {
      const own = route.path ? [route.path] : [];
      const children = (route.children || []).map((child) => child.path || "");
      return [...own, ...children];
    });
    expect(paths).toContain("/");
    expect(paths).toContain("/books/:bookId/whole-book-insights");
    expect(paths).toContain("/books/:bookId/pro-native-overview");
  });
});
