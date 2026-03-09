import assert from "node:assert/strict";
import test from "node:test";

import {
  narrowFilesByTestNamePattern,
  partitionRunnerArgs,
} from "../run-tests-lib.mjs";

test("test-name pattern narrows scoped runs when no explicit files are provided", () => {
  const selectedFiles = [
    "/tmp/tests/unit/runtimeRefreshController.test.ts",
    "/tmp/tests/unit/apiBaseUrl.test.ts",
  ];

  const narrowedFiles = narrowFilesByTestNamePattern({
    selectedFiles,
    nodeArgs: ["--test-name-pattern", "normalize"],
    positionalArgs: [],
    readFile(filePath: string) {
      if (filePath.endsWith("runtimeRefreshController.test.ts")) {
        return "test('refresh controller schedules polling', () => {})";
      }
      return "test('normalize trailing slash API URLs', () => {})";
    },
  });

  assert.deepEqual(narrowedFiles, ["/tmp/tests/unit/apiBaseUrl.test.ts"]);
});

test("test-name pattern does not override explicit file arguments", () => {
  const selectedFiles = ["/tmp/tests/unit/runtimeRefreshController.test.ts"];

  const narrowedFiles = narrowFilesByTestNamePattern({
    selectedFiles,
    nodeArgs: ["--test-name-pattern", "normalize"],
    positionalArgs: ["tests/unit/runtimeRefreshController.test.ts"],
    readFile() {
      return "test('normalize trailing slash API URLs', () => {})";
    },
  });

  assert.deepEqual(narrowedFiles, selectedFiles);
});

test("test-name pattern falls back to the original selection when no files match", () => {
  const selectedFiles = [
    "/tmp/tests/unit/runtimeRefreshController.test.ts",
    "/tmp/tests/e2e/scaffold-smoke.test.mjs",
  ];

  const narrowedFiles = narrowFilesByTestNamePattern({
    selectedFiles,
    nodeArgs: ["--test-name-pattern", "missing-pattern"],
    positionalArgs: [],
    readFile() {
      return "test('some unrelated assertion', () => {})";
    },
  });

  assert.deepEqual(narrowedFiles, selectedFiles);
});

test("runner argument partition keeps value-taking node flags out of positional args", () => {
  const parsed = partitionRunnerArgs([
    "--scope=unit",
    "--test-reporter",
    "spec",
    "--test-name-pattern",
    "normalize",
  ]);

  assert.deepEqual(parsed.customArgs, ["--scope=unit"]);
  assert.deepEqual(parsed.nodeArgs, [
    "--test-reporter",
    "spec",
    "--test-name-pattern",
    "normalize",
  ]);
  assert.deepEqual(parsed.positionalArgs, []);
});

test("runner argument partition preserves explicit file paths", () => {
  const parsed = partitionRunnerArgs([
    "--test-only",
    "tests/unit/runTestsLib.test.ts",
  ]);

  assert.deepEqual(parsed.nodeArgs, ["--test-only"]);
  assert.deepEqual(parsed.positionalArgs, ["tests/unit/runTestsLib.test.ts"]);
});
