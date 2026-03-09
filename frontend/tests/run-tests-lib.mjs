export function extractNamePattern(nodeArgs) {
  const patternIndex = nodeArgs.findIndex((arg) => arg === "--test-name-pattern");
  if (patternIndex >= 0) {
    return nodeArgs[patternIndex + 1] ?? null;
  }

  const inlinePatternArg = nodeArgs.find((arg) =>
    arg.startsWith("--test-name-pattern="),
  );
  if (!inlinePatternArg) {
    return null;
  }
  return inlinePatternArg.slice("--test-name-pattern=".length);
}

const NODE_FLAGS_WITH_SEPARATE_VALUES = new Set([
  "-C",
  "-r",
  "--conditions",
  "--debug-port",
  "--diagnostic-dir",
  "--disable-proto",
  "--disable-warning",
  "--dns-result-order",
  "--env-file",
  "--env-file-if-exists",
  "--experimental-config-file",
  "--experimental-loader",
  "--experimental-sea-config",
  "--heap-prof-dir",
  "--heap-prof-name",
  "--icu-data-dir",
  "--import",
  "--input-type",
  "--inspect-port",
  "--inspect-publish-uid",
  "--loader",
  "--localstorage-file",
  "--max-http-header-size",
  "--openssl-config",
  "--redirect-warnings",
  "--report-dir",
  "--report-directory",
  "--report-filename",
  "--report-signal",
  "--require",
  "--secure-heap",
  "--secure-heap-min",
  "--snapshot-blob",
  "--test-concurrency",
  "--test-coverage-branches",
  "--test-coverage-exclude",
  "--test-coverage-functions",
  "--test-coverage-include",
  "--test-coverage-lines",
  "--test-global-setup",
  "--test-isolation",
  "--test-name-pattern",
  "--test-reporter",
  "--test-reporter-destination",
  "--test-rerun-failures",
  "--test-shard",
  "--test-skip-pattern",
  "--test-timeout",
  "--title",
  "--tls-keylog",
  "--trace-event-categories",
  "--trace-event-file-pattern",
  "--trace-require-module",
  "--unhandled-rejections",
  "--use-largepages",
  "--watch-kill-signal",
  "--watch-path",
]);

export function partitionRunnerArgs(rawArgs) {
  const customArgs = [];
  const nodeArgs = [];
  const positionalArgs = [];

  for (let index = 0; index < rawArgs.length; index += 1) {
    const arg = rawArgs[index];
    if (arg.startsWith("--scope=")) {
      customArgs.push(arg);
      continue;
    }
    if (arg === "--scope") {
      customArgs.push(arg, rawArgs[index + 1] ?? "all");
      index += 1;
      continue;
    }
    if (arg.startsWith("-")) {
      nodeArgs.push(arg);
      if (NODE_FLAGS_WITH_SEPARATE_VALUES.has(arg) && rawArgs[index + 1]) {
        nodeArgs.push(rawArgs[index + 1]);
        index += 1;
      }
      continue;
    }
    positionalArgs.push(arg);
  }

  return { customArgs, nodeArgs, positionalArgs };
}

export function buildPatternMatcher(patternSource) {
  if (!patternSource) {
    return null;
  }

  try {
    return new RegExp(patternSource);
  } catch {
    return null;
  }
}

export function narrowFilesByTestNamePattern({
  selectedFiles,
  nodeArgs,
  positionalArgs,
  readFile,
}) {
  const namePattern = buildPatternMatcher(extractNamePattern(nodeArgs));
  if (!namePattern || positionalArgs.length > 0) {
    return selectedFiles;
  }

  const patternMatchedFiles = selectedFiles.filter((filePath) =>
    namePattern.test(readFile(filePath)),
  );
  return patternMatchedFiles.length > 0 ? patternMatchedFiles : selectedFiles;
}
