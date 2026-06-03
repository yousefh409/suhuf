import { describe, it, expect } from "vitest";
import { computeStats } from "./stats";
import type { SessionRow } from "./stats";

// Reference "now": 2026-06-03T12:00:00Z (UTC noon)
const NOW = new Date("2026-06-03T12:00:00Z");

function row(occurredAt: string, overrides: Partial<SessionRow> = {}): SessionRow {
  return {
    pagesRead: 5,
    wordsLearned: 10,
    durationSeconds: 300,
    occurredAt,
    ...overrides,
  };
}

describe("computeStats", () => {
  it("returns zeros when there are no sessions", () => {
    expect(computeStats([], NOW)).toEqual({
      pagesToday: 0,
      wordsLearnedThisWeek: 0,
      streakDays: 0,
      timeReadMinutes: 0,
    });
  });

  describe("pagesToday", () => {
    it("sums pagesRead for sessions on the same UTC calendar day as now", () => {
      const sessions = [
        row("2026-06-03T00:00:00Z", { pagesRead: 10 }),
        row("2026-06-03T11:59:59Z", { pagesRead: 7 }),
        row("2026-06-02T23:59:59Z", { pagesRead: 99 }), // yesterday — excluded
      ];
      const stats = computeStats(sessions, NOW);
      expect(stats.pagesToday).toBe(17);
    });

    it("excludes sessions from yesterday", () => {
      const sessions = [row("2026-06-02T20:00:00Z", { pagesRead: 50 })];
      expect(computeStats(sessions, NOW).pagesToday).toBe(0);
    });
  });

  describe("wordsLearnedThisWeek", () => {
    it("sums wordsLearned from the last 7×24h", () => {
      const sessions = [
        row("2026-06-03T11:00:00Z", { wordsLearned: 20 }), // within 7 days
        row("2026-05-27T12:00:01Z", { wordsLearned: 5 }),  // just inside 7 days
        row("2026-05-27T11:59:59Z", { wordsLearned: 999 }), // just outside — excluded
      ];
      const stats = computeStats(sessions, NOW);
      expect(stats.wordsLearnedThisWeek).toBe(25);
    });

    it("includes sessions exactly at the 7-day boundary", () => {
      const boundary = new Date(NOW.getTime() - 7 * 24 * 60 * 60 * 1000);
      const sessions = [row(boundary.toISOString(), { wordsLearned: 3 })];
      expect(computeStats(sessions, NOW).wordsLearnedThisWeek).toBe(3);
    });
  });

  describe("streakDays", () => {
    it("counts a 3-day streak ending today", () => {
      const sessions = [
        row("2026-06-03T09:00:00Z"), // today
        row("2026-06-02T10:00:00Z"), // yesterday
        row("2026-06-01T08:00:00Z"), // 2 days ago
      ];
      expect(computeStats(sessions, NOW).streakDays).toBe(3);
    });

    it("a gap breaks the streak", () => {
      const sessions = [
        row("2026-06-03T09:00:00Z"), // today
        row("2026-06-02T10:00:00Z"), // yesterday
        // gap on 2026-06-01
        row("2026-05-31T08:00:00Z"), // before gap
      ];
      expect(computeStats(sessions, NOW).streakDays).toBe(2);
    });

    it("counts streak ending yesterday when today has no session", () => {
      const sessions = [
        row("2026-06-02T20:00:00Z"), // yesterday
        row("2026-06-01T09:00:00Z"), // 2 days ago
      ];
      expect(computeStats(sessions, NOW).streakDays).toBe(2);
    });

    it("returns 0 when most recent session is older than yesterday", () => {
      const sessions = [row("2026-06-01T09:00:00Z")]; // 2 days ago
      expect(computeStats(sessions, NOW).streakDays).toBe(0);
    });

    it("returns 1 for a single session today", () => {
      const sessions = [row("2026-06-03T09:00:00Z")];
      expect(computeStats(sessions, NOW).streakDays).toBe(1);
    });

    it("multiple sessions on the same day count as 1 streak day", () => {
      const sessions = [
        row("2026-06-03T08:00:00Z"),
        row("2026-06-03T10:00:00Z"),
        row("2026-06-02T09:00:00Z"),
      ];
      expect(computeStats(sessions, NOW).streakDays).toBe(2);
    });
  });

  describe("timeReadMinutes", () => {
    it("sums durationSeconds for today and rounds to minutes", () => {
      const sessions = [
        row("2026-06-03T08:00:00Z", { durationSeconds: 600 }),  // 10 min
        row("2026-06-03T09:00:00Z", { durationSeconds: 1800 }), // 30 min
        row("2026-06-02T10:00:00Z", { durationSeconds: 9999 }), // yesterday — excluded
      ];
      expect(computeStats(sessions, NOW).timeReadMinutes).toBe(40);
    });

    it("rounds correctly: 90s → 2min", () => {
      const sessions = [row("2026-06-03T10:00:00Z", { durationSeconds: 90 })];
      expect(computeStats(sessions, NOW).timeReadMinutes).toBe(2);
    });

    it("returns 0 when no sessions today", () => {
      const sessions = [row("2026-06-02T10:00:00Z", { durationSeconds: 3600 })];
      expect(computeStats(sessions, NOW).timeReadMinutes).toBe(0);
    });
  });
});
