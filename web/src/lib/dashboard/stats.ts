import "server-only";

import { createClient } from "@/lib/supabase/server";
import type { DashboardStats } from "./types";

export type SessionRow = {
  pagesRead: number;
  wordsLearned: number;
  durationSeconds: number;
  occurredAt: string;
};

/** Return the UTC calendar day string "YYYY-MM-DD" for a Date or ISO string */
function utcDay(d: Date | string): string {
  const dt = typeof d === "string" ? new Date(d) : d;
  return dt.toISOString().slice(0, 10);
}

export function computeStats(sessions: SessionRow[], now: Date): DashboardStats {
  const todayStr = utcDay(now);
  const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

  let pagesToday = 0;
  let wordsLearnedThisWeek = 0;
  let durationTodaySeconds = 0;

  // Collect unique days that have ≥1 session (as Set of "YYYY-MM-DD")
  const activeDays = new Set<string>();

  for (const s of sessions) {
    const day = utcDay(s.occurredAt);
    const ts = new Date(s.occurredAt);

    activeDays.add(day);

    if (day === todayStr) {
      pagesToday += s.pagesRead;
      durationTodaySeconds += s.durationSeconds;
    }

    if (ts >= weekAgo) {
      wordsLearnedThisWeek += s.wordsLearned;
    }
  }

  // Compute streak
  const streakDays = computeStreak(activeDays, now);
  const timeReadMinutes = Math.round(durationTodaySeconds / 60);

  return { pagesToday, wordsLearnedThisWeek, streakDays, timeReadMinutes };
}

function computeStreak(activeDays: Set<string>, now: Date): number {
  if (activeDays.size === 0) return 0;

  const todayStr = utcDay(now);
  const yesterdayStr = utcDay(new Date(now.getTime() - 24 * 60 * 60 * 1000));

  // Streak must end on today or yesterday
  let cursor: string;
  if (activeDays.has(todayStr)) {
    cursor = todayStr;
  } else if (activeDays.has(yesterdayStr)) {
    cursor = yesterdayStr;
  } else {
    return 0;
  }

  let streak = 0;
  while (activeDays.has(cursor)) {
    streak++;
    // Move back one day
    const prev = new Date(cursor + "T00:00:00Z");
    prev.setUTCDate(prev.getUTCDate() - 1);
    cursor = utcDay(prev);
  }

  return streak;
}

export async function queryStats(): Promise<DashboardStats> {
  const empty: DashboardStats = {
    pagesToday: 0,
    wordsLearnedThisWeek: 0,
    streakDays: 0,
    timeReadMinutes: 0,
  };

  const sb = await createClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return empty;

  const since = new Date(Date.now() - 60 * 24 * 60 * 60 * 1000).toISOString();

  const { data, error } = await sb
    .from("reading_sessions")
    .select("pages_read, words_learned, duration_seconds, occurred_at")
    .eq("user_id", user.id)
    .gte("occurred_at", since);

  if (error) {
    console.error("[stats] queryStats error:", error.message);
    return empty;
  }

  type RawSession = {
    pages_read: number;
    words_learned: number;
    duration_seconds: number;
    occurred_at: string;
  };

  const rows: SessionRow[] = (data as RawSession[]).map((r) => ({
    pagesRead: r.pages_read,
    wordsLearned: r.words_learned,
    durationSeconds: r.duration_seconds,
    occurredAt: r.occurred_at,
  }));

  return computeStats(rows, new Date());
}
