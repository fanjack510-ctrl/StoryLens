import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { SettingsAppearanceTab } from "./SettingsAppearanceTab";
import { INTERFACE_ZOOM_STORAGE_KEY } from "../../lib/interfaceZoom";
import { useUiStore } from "../../stores/uiStore";

vi.mock("../../services/settingsApi", () => ({
  settingsApi: {
    save: vi.fn(async () => ({})),
  },
}));

describe("SettingsAppearanceTab interface zoom", () => {
  beforeEach(() => {
    localStorage.clear();
    useUiStore.setState({
      interfaceZoom: 80,
      fontSize: 17,
      lineHeight: 1.9,
      theme: "light",
      demo: false,
      contentWidth: "wide",
      showParagraphIds: false,
    });
    document.documentElement.style.zoom = "";
  });

  afterEach(() => {
    cleanup();
  });

  it("renders zoom control and changes level immediately", async () => {
    render(
      <MemoryRouter>
        <SettingsAppearanceTab />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("interface-zoom-control")).toBeInTheDocument();
    expect(screen.getByLabelText("正文字号")).toBeInTheDocument();
    expect(screen.getByTestId("interface-zoom-preset-100")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("interface-zoom-preset-125"));
    await waitFor(() => expect(useUiStore.getState().interfaceZoom).toBe(125));
    expect(localStorage.getItem(INTERFACE_ZOOM_STORAGE_KEY)).toBe("125");
    expect(document.documentElement.style.zoom).toBe("1.25");
    // reading settings stay independent
    expect(useUiStore.getState().fontSize).toBe(17);
    expect(useUiStore.getState().lineHeight).toBe(1.9);
  });

  it("increase/decrease clamp at ends", async () => {
    render(
      <MemoryRouter>
        <SettingsAppearanceTab />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("interface-zoom-preset-150"));
    await waitFor(() => expect(useUiStore.getState().interfaceZoom).toBe(150));
    expect(screen.getByTestId("interface-zoom-increase")).toBeDisabled();

    fireEvent.click(screen.getByTestId("interface-zoom-preset-80"));
    await waitFor(() => expect(useUiStore.getState().interfaceZoom).toBe(80));
    expect(screen.getByTestId("interface-zoom-decrease")).toBeDisabled();
  });

  it("reset restores product default 80%", async () => {
    useUiStore.setState({ interfaceZoom: 110 });
    render(
      <MemoryRouter>
        <SettingsAppearanceTab />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("interface-zoom-reset")).toHaveTextContent("恢复默认（80%）");
    fireEvent.click(screen.getByTestId("interface-zoom-reset"));
    await waitFor(() => expect(useUiStore.getState().interfaceZoom).toBe(80));
    expect(localStorage.getItem(INTERFACE_ZOOM_STORAGE_KEY)).toBe("80");
  });

  it("keeps manually selected 100% as a normal option", async () => {
    render(
      <MemoryRouter>
        <SettingsAppearanceTab />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("interface-zoom-preset-100"));
    await waitFor(() => expect(useUiStore.getState().interfaceZoom).toBe(100));
    expect(localStorage.getItem(INTERFACE_ZOOM_STORAGE_KEY)).toBe("100");
  });
});
