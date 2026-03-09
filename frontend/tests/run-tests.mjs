import { readFileSync, readdirSync, statSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import process from "node:process";

import {
  narrowFilesByTestNamePattern,
  partitionRunnerArgs,
} from "./run-tests-lib.mjs";

const TEST_ROOT = path.resolve("tests");
const DEFAULT_SCOPES = ["unit", "e2e"];
const TEST_FILE_PATTERN = /\.test\.(?:[cm]?[jt]sx?)$/;

function walkTests(rootDir) {
  const discovered = [];
  const entries = readdirSync(rootDir, { withFileTypes: true }).sort((left, right) =>
    left.name.localeCompare(right.name),
  );

  for (const entry of entries) {
    const entryPath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      discovered.push(...walkTests(entryPath));
      continue;
    }
    if (entry.isFile() && TEST_FILE_PATTERN.test(entry.name)) {
      discovered.push(entryPath);
    }
  }

  return discovered;
}

function expandPath(candidatePath) {
  const resolvedPath = path.resolve(candidatePath);
  const stats = statSync(resolvedPath);
  if (stats.isDirectory()) {
    return walkTests(resolvedPath);
  }
  return [resolvedPath];
}

function discoverScopedFiles(scopes) {
  return scopes.flatMap((scope) => walkTests(path.join(TEST_ROOT, scope)));
}

const rawArgs = process.argv.slice(2);
const { customArgs, nodeArgs, positionalArgs } = partitionRunnerArgs(rawArgs);

const scopeArg = (() => {
  const inlineScope = customArgs.find((arg) => arg.startsWith("--scope="));
  if (inlineScope) {
    return inlineScope.slice("--scope=".length);
  }
  const scopeIndex = customArgs.findIndex((arg) => arg === "--scope");
  if (scopeIndex >= 0) {
    return customArgs[scopeIndex + 1] ?? "all";
  }
  return "all";
})();

const scopes =
  scopeArg === "all" ? DEFAULT_SCOPES : scopeArg.split(",").filter(Boolean);

let selectedFiles = positionalArgs.length
  ? positionalArgs.flatMap((candidatePath) => expandPath(candidatePath))
  : discoverScopedFiles(scopes);

selectedFiles = narrowFilesByTestNamePattern({
  selectedFiles,
  nodeArgs,
  positionalArgs,
  readFile(filePath) {
    return readFileSync(filePath, "utf-8");
  },
});

const relativeFiles = [...new Set(selectedFiles)]
  .sort((left, right) => left.localeCompare(right))
  .map((filePath) => path.relative(process.cwd(), filePath));

const result = spawnSync(
  process.execPath,
  ["--experimental-strip-types", "--test", ...nodeArgs, ...relativeFiles],
  {
    stdio: "inherit",
  },
);

process.exit(result.status ?? 1);
