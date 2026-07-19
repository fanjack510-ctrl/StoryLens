import "@testing-library/jest-dom/vitest";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

global.ResizeObserver = ResizeObserverMock as typeof ResizeObserver;

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: query.includes("min-width: 1280px"),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

const elementProto = Element.prototype as Element & {
  scrollIntoView?: (options?: ScrollIntoViewOptions) => void;
};
if (!elementProto.scrollIntoView) {
  elementProto.scrollIntoView = () => {};
}
