import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import Home from "../../src/app/page";

test("Home renders navigation cards", () => {
  render(<Home />);
  expect(screen.getByText("Overview")).toBeDefined();
  expect(screen.getByText("Repositories")).toBeDefined();
  expect(screen.getByText("Settings & Configuration")).toBeDefined();
});
