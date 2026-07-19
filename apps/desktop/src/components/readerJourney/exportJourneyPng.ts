export type JourneyExportErrorCode =
  | "root_missing"
  | "not_rendered"
  | "image_failed"
  | "download_failed"
  | "unknown";

export const JOURNEY_EXPORT_USER_MESSAGES: Record<JourneyExportErrorCode, string> = {
  root_missing: "未找到可导出的旅程图",
  not_rendered: "旅程图尚未完成渲染",
  image_failed: "图像生成失败",
  download_failed: "浏览器未能触发下载",
  unknown: "导出过程中发生未知错误",
};

export class JourneyExportError extends Error {
  readonly code: JourneyExportErrorCode;
  readonly userMessage: string;

  constructor(code: JourneyExportErrorCode, cause?: unknown) {
    super(JOURNEY_EXPORT_USER_MESSAGES[code]);
    this.name = "JourneyExportError";
    this.code = code;
    this.userMessage = JOURNEY_EXPORT_USER_MESSAGES[code];
    if (cause !== undefined) {
      (this as Error & { cause?: unknown }).cause = cause;
    }
  }
}

export type JourneyExportResult = {
  filename: string;
};

function sanitizeChapterTitle(title: string): string {
  const stripped = Array.from(title.trim())
    .filter((char) => {
      const code = char.charCodeAt(0);
      return code >= 32 && code !== 127 && !/[<>:"/\\|?*]/.test(char);
    })
    .join("");
  const cleaned = stripped.replace(/\s+/g, "_").slice(0, 80);
  return cleaned || "Chapter";
}

function resolveExportRoot(root: HTMLElement | SVGElement): HTMLElement {
  if (root instanceof SVGElement) {
    const wrapper = document.createElement("div");
    wrapper.appendChild(root.cloneNode(true));
    return wrapper;
  }
  const nested =
    root.querySelector<HTMLElement>('[data-reader-journey-export-root="true"]') ??
    root.querySelector<HTMLElement>('[data-testid="journey-export-root"]');
  return nested ?? root;
}

function inlineComputedStyles(source: Element, target: Element) {
  if (!(source instanceof HTMLElement || source instanceof SVGElement)) return;
  if (!(target instanceof HTMLElement || target instanceof SVGElement)) return;
  const computed = window.getComputedStyle(source);
  let cssText = "";
  for (let i = 0; i < computed.length; i += 1) {
    const prop = computed.item(i);
    if (!prop) continue;
    cssText += `${prop}:${computed.getPropertyValue(prop)};`;
  }
  target.setAttribute("style", cssText);
  const sourceChildren = Array.from(source.children);
  const targetChildren = Array.from(target.children);
  const count = Math.min(sourceChildren.length, targetChildren.length);
  for (let i = 0; i < count; i += 1) {
    inlineComputedStyles(sourceChildren[i]!, targetChildren[i]!);
  }
}

function requiresJourneyChart(element: HTMLElement): boolean {
  return (
    element.getAttribute("data-reader-journey-export-root") === "true" ||
    element.getAttribute("data-testid") === "journey-export-root" ||
    element.querySelector('[data-testid="journey-curve-svg"]') != null ||
    element.querySelector('[data-testid="journey-curve-svg-full-export"]') != null
  );
}

function findExportSvg(element: HTMLElement): SVGSVGElement | null {
  return (
    element.querySelector<SVGSVGElement>('[data-testid="journey-curve-svg-full-export"]') ??
    element.querySelector<SVGSVGElement>('[data-testid="journey-curve-svg"]')
  );
}

function assertExportReady(element: HTMLElement) {
  const rect = element.getBoundingClientRect();
  const width = rect.width || element.clientWidth || element.scrollWidth;
  const height = rect.height || element.clientHeight || element.scrollHeight;
  if (requiresJourneyChart(element)) {
    const svg = findExportSvg(element) ?? element.querySelector("svg");
    if (!svg) {
      throw new JourneyExportError("not_rendered");
    }
    const attrW = Number(svg.getAttribute("width"));
    const attrH = Number(svg.getAttribute("height"));
    if (attrW > 0 && attrH > 0) return;
    const svgBox = svg.getBoundingClientRect();
    if ((width > 0 || height > 0) && (svgBox.width <= 0 || svgBox.height <= 0)) {
      throw new JourneyExportError("not_rendered");
    }
    return;
  }
  if (width <= 0 || height <= 0) {
    throw new JourneyExportError("not_rendered");
  }
}

function triggerDownload(href: string, filename: string) {
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => resolve(image);
    image.onerror = () => reject(new JourneyExportError("image_failed"));
    image.src = url;
  });
}

async function canvasToPngBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((result) => {
      if (result) resolve(result);
      else reject(new JourneyExportError("image_failed"));
    }, "image/png");
  });
}

async function rasterizeForeignObject(
  element: HTMLElement,
  width: number,
  height: number,
  scale: number,
): Promise<HTMLCanvasElement> {
  const clone = element.cloneNode(true) as HTMLElement;
  try {
    inlineComputedStyles(element, clone);
  } catch {
    /* best-effort */
  }
  clone.setAttribute("xmlns", "http://www.w3.org/1999/xhtml");
  clone.style.width = `${width}px`;
  clone.style.height = `${height}px`;
  clone.style.background = "#ffffff";

  const serialized = new XMLSerializer().serializeToString(clone);
  const svgMarkup = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width * scale}" height="${height * scale}">
  <foreignObject width="${width}" height="${height}" transform="scale(${scale})">
    ${serialized}
  </foreignObject>
</svg>`;
  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgMarkup)}`;
  const image = await loadImage(url);

  const canvas = document.createElement("canvas");
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new JourneyExportError("image_failed");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, 0, 0);
  return canvas;
}

async function rasterizeSvgFallback(
  element: HTMLElement,
  width: number,
  height: number,
  scale: number,
  chapterTitle?: string,
): Promise<HTMLCanvasElement> {
  const svg = findExportSvg(element) ?? element.querySelector("svg");
  if (!svg) {
    throw new JourneyExportError("not_rendered");
  }

  const title =
    element.querySelector('[data-testid="journey-export-title"]')?.textContent?.trim() ||
    chapterTitle ||
    "Reader Journey";
  const meta =
    element.querySelector('[data-testid="journey-export-meta"]')?.textContent?.trim() || "";
  const summaryText = Array.from(
    element.querySelectorAll('[data-testid="journey-summary-cards"] .journey-summary-card'),
  )
    .map((card) => card.textContent?.replace(/\s+/g, " ").trim() || "")
    .filter(Boolean)
    .join("  |  ");

  const headerHeight = 72;
  const attrW = Number(svg.getAttribute("width"));
  const attrH = Number(svg.getAttribute("height"));
  const svgBox = svg.getBoundingClientRect();
  const svgWidth = Math.max(Math.ceil(attrW || svgBox.width || width), 1);
  const svgHeight = Math.max(Math.ceil(attrH || svgBox.height || 360), 1);

  const clone = svg.cloneNode(true) as SVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  if (!clone.getAttribute("width")) clone.setAttribute("width", String(svgWidth));
  if (!clone.getAttribute("height")) clone.setAttribute("height", String(svgHeight));
  const svgMarkup = new XMLSerializer().serializeToString(clone);
  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgMarkup)}`;
  const image = await loadImage(url);

  const canvas = document.createElement("canvas");
  canvas.width = Math.max(width, svgWidth) * scale;
  canvas.height = (headerHeight + svgHeight) * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new JourneyExportError("image_failed");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.scale(scale, scale);
  ctx.fillStyle = "#222222";
  ctx.font = "600 16px sans-serif";
  ctx.fillText(title.slice(0, 80), 16, 24);
  ctx.font = "12px sans-serif";
  ctx.fillStyle = "#666666";
  if (meta) ctx.fillText(meta.slice(0, 120), 16, 44);
  if (summaryText) ctx.fillText(summaryText.slice(0, 160), 16, 62);
  ctx.drawImage(image, 0, headerHeight, svgWidth, svgHeight);
  return canvas;
}

export type JourneyExportOptions = {
  /** full_journey (default): entire scene span, Y 0–100, independent of viewport zoom. */
  mode?: "full_journey" | "current_viewport";
};

function measureExportSize(element: HTMLElement, mode: "full_journey" | "current_viewport") {
  const svg = findExportSvg(element);
  if (mode === "full_journey" && svg) {
    const attrW = Number(svg.getAttribute("width"));
    const attrH = Number(svg.getAttribute("height"));
    const width = Math.max(
      Math.ceil(attrW || svg.scrollWidth || element.scrollWidth || 720),
      1,
    );
    const header = Math.ceil(
      (element.querySelector('[data-testid="journey-export-title"]') as HTMLElement | null)
        ?.offsetHeight ?? 72,
    );
    const height = Math.max(
      Math.ceil((attrH || svg.scrollHeight || 360) + header + 24),
      1,
    );
    return { width, height };
  }
  const rect = element.getBoundingClientRect();
  const width = Math.max(
    Math.ceil(element.scrollWidth || rect.width || 520),
    1,
  );
  const height = Math.max(
    Math.ceil(element.scrollHeight || rect.height || 260),
    1,
  );
  return { width, height };
}

export async function exportJourneyPng(
  root: HTMLElement | SVGElement,
  chapterTitle?: string,
  options: JourneyExportOptions = {},
): Promise<JourneyExportResult> {
  if (!root) {
    throw new JourneyExportError("root_missing");
  }

  const mode = options.mode ?? "full_journey";
  const element = resolveExportRoot(root);
  if (!(element instanceof HTMLElement)) {
    throw new JourneyExportError("root_missing");
  }

  assertExportReady(element);

  const { width, height } = measureExportSize(element, mode);
  const scale = 2;

  let canvas: HTMLCanvasElement;
  try {
    canvas = await rasterizeForeignObject(element, width, height, scale);
  } catch (foreignError) {
    const canSvgFallback =
      requiresJourneyChart(element) && element.querySelector("svg") != null;
    if (!canSvgFallback) {
      if (foreignError instanceof JourneyExportError) throw foreignError;
      throw new JourneyExportError("image_failed", foreignError);
    }
    try {
      canvas = await rasterizeSvgFallback(element, width, height, scale, chapterTitle);
    } catch (fallbackError) {
      if (fallbackError instanceof JourneyExportError) throw fallbackError;
      if (foreignError instanceof JourneyExportError) throw foreignError;
      throw new JourneyExportError("image_failed", fallbackError);
    }
  }

  if (canvas.width <= 0 || canvas.height <= 0) {
    throw new JourneyExportError("image_failed");
  }

  let pngBlob: Blob;
  try {
    pngBlob = await canvasToPngBlob(canvas);
  } catch (error) {
    if (error instanceof JourneyExportError) throw error;
    throw new JourneyExportError("image_failed", error);
  }

  const safeTitle = sanitizeChapterTitle(chapterTitle ?? "Chapter");
  const filename =
    mode === "full_journey"
      ? `StoryLens_${safeTitle}_完整旅程_v4.0.png`
      : `StoryLens_${safeTitle}_当前视图_v4.0.png`;
  const href = URL.createObjectURL(pngBlob);
  try {
    triggerDownload(href, filename);
  } catch (error) {
    URL.revokeObjectURL(href);
    throw new JourneyExportError("download_failed", error);
  }

  window.setTimeout(() => URL.revokeObjectURL(href), 2000);
  return { filename };
}
