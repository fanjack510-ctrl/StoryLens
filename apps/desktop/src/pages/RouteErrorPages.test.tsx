import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { NotFoundPage, RouteErrorPage } from "./RouteErrorPages";

afterEach(cleanup);

describe("RouteErrorPages", () => {
  it("renders Chinese 404 with reload and library actions", () => {
    const router = createMemoryRouter(
      [
        { path: "/", element: <div>home</div> },
        { path: "*", element: <NotFoundPage /> },
      ],
      { initialEntries: ["/missing-route"] },
    );
    render(<RouterProvider router={router} />);
    expect(screen.getByTestId("not-found-page")).toHaveTextContent("页面未找到");
    expect(screen.getByTestId("not-found-library")).toBeInTheDocument();
    expect(screen.getByTestId("not-found-reload")).toBeInTheDocument();
  });

  it("renders Chinese runtime error page without stack in production-like render", () => {
    const Boom = () => {
      throw new Error("boom at C:\\Users\\dev\\storylens\\src\\Foo.tsx:12");
    };
    const router = createMemoryRouter(
      [
        {
          path: "/",
          element: <Boom />,
          errorElement: <RouteErrorPage />,
        },
        { path: "/library", element: <div>library</div> },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);
    const page = screen.getByTestId("route-error-page");
    expect(page).toHaveTextContent("页面出错了");
    expect(page).not.toHaveTextContent("Foo.tsx");
    expect(page).not.toHaveTextContent("localhost");
    expect(page).not.toHaveTextContent("C:\\Users");
    expect(screen.getByTestId("route-error-reload")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("route-error-library"));
    expect(screen.getByText("library")).toBeInTheDocument();
  });
});
