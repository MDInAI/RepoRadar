import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
  formatAnalysisStatusLabel,
  formatCompactNumber,
  formatDiscoverySourceLabel,
  formatMonetizationLabel,
  formatRelativeDate,
  getFitBadgeClassName,
  getSourceBadgeClassName,
  getStatusBadgeClassName,
} from "@/components/repositories/catalogPresentation";

describe("catalogPresentation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-09T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  test("formats compact numbers and enum labels", () => {
    expect(formatCompactNumber(0)).toBe("0");
    expect(formatCompactNumber(12500)).toBe("12,500");
    expect(formatDiscoverySourceLabel("firehose")).toBe("Firehose");
    expect(formatDiscoverySourceLabel("unknown")).toBe("Unknown");
    expect(formatAnalysisStatusLabel("in_progress")).toBe("In Progress");
    expect(formatMonetizationLabel(null)).toBe("Unscored");
    expect(formatMonetizationLabel("high")).toBe("High");
  });

  test("formats relative dates and handles null or invalid values", () => {
    expect(formatRelativeDate(null)).toBe("No activity");
    expect(formatRelativeDate("not-a-date")).toBe("Unknown");
    expect(formatRelativeDate("2026-03-09T11:00:00Z")).toBe("1 hour ago");
    expect(formatRelativeDate("2026-03-08T12:00:00Z")).toBe("yesterday");
  });

  test("returns badge class names for source, status, and fit values", () => {
    expect(getSourceBadgeClassName("backfill")).toContain("sky");
    expect(getSourceBadgeClassName("unknown")).toContain("slate");
    expect(getStatusBadgeClassName("completed")).toContain("emerald");
    expect(getStatusBadgeClassName("pending")).toContain("slate");
    expect(getFitBadgeClassName("medium")).toContain("amber");
    expect(getFitBadgeClassName(null)).toContain("slate");
  });
});
