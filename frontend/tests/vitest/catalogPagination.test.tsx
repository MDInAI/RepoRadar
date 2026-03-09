import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { CatalogPagination } from "@/components/repositories/CatalogPagination";

describe("CatalogPagination", () => {
  afterEach(() => {
    cleanup();
  });

  test("renders pagination state and dispatches page and page-size changes", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();
    const onPageSizeChange = vi.fn();

    render(
      <CatalogPagination
        page={2}
        totalPages={4}
        pageSize={30}
        totalCount={120}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
      />,
    );

    expect(screen.getByText("Page 2 of 4")).toBeTruthy();
    expect(screen.getByText("120 total repositories")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(onPageChange).toHaveBeenCalledWith(1);

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(onPageChange).toHaveBeenCalledWith(3);

    await user.selectOptions(screen.getByLabelText("Rows per page"), "100");
    expect(onPageSizeChange).toHaveBeenCalledWith(100);
  });

  test("disables navigation at the catalog boundaries", () => {
    const { rerender } = render(
      <CatalogPagination
        page={1}
        totalPages={3}
        pageSize={30}
        totalCount={90}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Previous" })).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Next" })).toHaveProperty("disabled", false);

    rerender(
      <CatalogPagination
        page={3}
        totalPages={3}
        pageSize={30}
        totalCount={90}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Previous" })).toHaveProperty("disabled", false);
    expect(screen.getByRole("button", { name: "Next" })).toHaveProperty("disabled", true);
  });
});
