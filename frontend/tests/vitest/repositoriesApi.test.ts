import { describe, expect, test } from "vitest";

import {
  RepositoryCatalogRequestError,
  buildRepositoryCatalogSearchParams,
  getRepositoryCatalogQueryKey,
  parseRepositoryCatalogSearchParams,
} from "@/api/repositories";

describe("repositories api helpers", () => {
  test("keeps missing request error codes undefined", () => {
    const error = new RepositoryCatalogRequestError("bad request", {
      status: 400,
    });

    expect(error.code).toBeUndefined();
    expect(error.details).toEqual({});
  });

  test("parses non-negative star filters from URL params", () => {
    const state = parseRepositoryCatalogSearchParams(
      new URLSearchParams("minStars=0&maxStars=500&starredOnly=true"),
    );

    expect(state.minStars).toBe(0);
    expect(state.maxStars).toBe(500);
    expect(state.starredOnly).toBe(true);
    expect(getRepositoryCatalogQueryKey(state)).toContain(0);
    expect(getRepositoryCatalogQueryKey(state)).toContain(500);
    expect(getRepositoryCatalogQueryKey(state)).toContain(true);
    expect(buildRepositoryCatalogSearchParams(state).get("starredOnly")).toBe("true");
  });
});
