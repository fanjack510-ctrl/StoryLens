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

  it("已确认之后不再占一个按钮位", async () => {

    // 它是一道**门**，不是常用动作——门开着的时候，门不该一直站在路中间。

    // 要改的人在「更多」里找得到。

    vi.spyOn(profileApi, "getBookProfile").mockResolvedValue({ status: "confirmed" } as never);

    render(

      <MemoryRouter>

        <BookProfileEntry bookId={7} />

      </MemoryRouter>,

    );

    await waitFor(() =>

      expect(screen.queryByTestId("book-profile-entry")).not.toBeInTheDocument(),

    );

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

it("从没建过画像的书，也要看得见这道门", async () => {
  // `getBookProfile` 对没建过画像的书返回 null——那是**最**未确认的状态，不是「不确定」。
  // 曾经把 null 当成「别拦」，于是新导入的书连入口都没有：只有点分析、在弹窗里撞 409，
  // 才第一次知道有画像这回事。而那正是这个组件存在的理由。
  vi.spyOn(profileApi, "getBookProfile").mockResolvedValue(null);
  render(
    <MemoryRouter>
      <BookProfileEntry bookId={7} />
    </MemoryRouter>,
  );
  const entry = await screen.findByTestId("book-profile-entry");
  expect(entry).toHaveTextContent("待确认");
  expect(entry).toHaveAttribute("data-state", "unconfirmed");
});
