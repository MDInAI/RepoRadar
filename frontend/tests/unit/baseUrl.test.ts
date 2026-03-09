import assert from "node:assert/strict";
import test from "node:test";

import {
  getRequiredApiBaseUrl,
  normalizeApiBaseUrl,
} from "../../src/api/base-url.ts";

test("normalizeApiBaseUrl removes trailing slashes once", () => {
  assert.equal(normalizeApiBaseUrl("http://localhost:8000/"), "http://localhost:8000");
  assert.equal(
    normalizeApiBaseUrl("http://localhost:8000///"),
    "http://localhost:8000",
  );
  assert.equal(
    normalizeApiBaseUrl("http://localhost:8000/api"),
    "http://localhost:8000/api",
  );
});

test("getRequiredApiBaseUrl throws when NEXT_PUBLIC_API_URL is missing", () => {
  assert.throws(
    () => getRequiredApiBaseUrl(undefined),
    /NEXT_PUBLIC_API_URL is required but not configured\./,
  );
});
