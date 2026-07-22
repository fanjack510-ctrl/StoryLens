import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useProductEdition } from "../../hooks/useProductEdition";
import { documentTitleForEdition, type ProductEdition } from "../../services/productEdition";
import { isTauriRuntime } from "../../services/desktopRuntime";

const PAGE_TITLES: Array<{ match: RegExp; title: string }> = [
  { match: /^\/library(\/|$)/, title: "我的书库" },
  { match: /^\/settings(\/|$)/, title: "设置" },
  { match: /^\/tasks(\/|$)/, title: "任务中心" },
  { match: /^\/workspace(\/|$)/, title: "工作台" },
  { match: /^\/books\//, title: "书籍" },
];

function pageTitleFromPath(pathname: string): string | null {
  for (const item of PAGE_TITLES) {
    if (item.match.test(pathname)) return item.title;
  }
  return null;
}

async function syncNativeWindowTitle(title: string): Promise<void> {
  if (!isTauriRuntime()) return;
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().setTitle(title);
  } catch {
    // Title sync is best-effort; never block the UI.
  }
}

/** Keeps document.title (and Tauri window title) aligned with unified edition state. */
export function DocumentTitleSync() {
  const location = useLocation();
  const edition = useProductEdition();
  const titleEdition: ProductEdition =
    !edition.loaded ? "free" : edition.is_pro ? "pro" : "free";

  useEffect(() => {
    if (!edition.loaded) {
      // Keep generic brand during first load to avoid free→Pro flicker in the title.
      document.title = "StoryLens";
      void syncNativeWindowTitle("StoryLens");
      return;
    }
    const title = documentTitleForEdition(titleEdition, pageTitleFromPath(location.pathname));
    document.title = title;
    void syncNativeWindowTitle(title);
  }, [edition.loaded, titleEdition, location.pathname]);

  return null;
}
