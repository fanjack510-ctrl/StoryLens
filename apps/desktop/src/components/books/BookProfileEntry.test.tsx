import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BookProfileEntry } from "./BookProfileEntry";
import * as profileApi from "../../features/bookProfile/api";

afterEach(cleanup);

describe("作品画像工具栏入口（CHG-20260815-095）", () => {
  it("未确认时把自己标成待办，并带上本章来路", async () => {
    vi.spyOn(profileApi, "getBookProfile").mockResolvedValue(null);
    render(
      <MemoryRouter>
        <BookProfileEntry bookId={2} chapterId={807} />
      </MemoryRouter>,
    );
    const entry = await screen.findByTestId("book-profile-entry");
    expect(entry).toHaveAttribute("data-state", "unconfirmed");
    expect(entry).toHaveTextContent("待确认");
    // Confirming from here must return to the chapter the user was reading.
    expect(entry).toHaveAttribute("href", "/books/2/profile?from=chapter&chapterId=807");
  });

  it("已确认时退成普通入口", async () => {
    vi.spyOn(profileApi, "getBookProfile").mockResolvedValue({
      status: "confirmed",
      axes: {},
      options: [],
      active_deltas: [],
    } as never);
    render(
      <MemoryRouter>
        <BookProfileEntry bookId={2} />
      </MemoryRouter>,
    );
    const entry = await screen.findByTestId("book-profile-entry");
    expect(entry).toHaveAttribute("data-state", "confirmed");
    expect(entry).toHaveAttribute("href", "/books/2/profile");
  });

  it("后端读不出来时不渲染——不能因为读失败就催用户去确认", async () => {
    vi.spyOn(profileApi, "getBookProfile").mockRejectedValue(new Error("offline"));
    render(
      <MemoryRouter>
        <BookProfileEntry bookId={2} />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.queryByTestId("book-profile-entry")).not.toBeInTheDocument(),
    );
  });
});
