import { create } from 'zustand';
import { getTodayStats, incrementStat } from '../lib/database';
import type { DayStats } from '../types';

interface StatsState {
  today: DayStats;
  weeklyWords: number;
  streak: number;
  totalTimeToday: string;

  loadStats: () => Promise<void>;
  recordPageRead: () => Promise<void>;
  recordWordLearned: () => Promise<void>;
  recordTime: (seconds: number) => Promise<void>;
}

export const useStatsStore = create<StatsState>((set, get) => ({
  today: { date: '', pages_read: 0, words_learned: 0, time_seconds: 0 },
  weeklyWords: 0,
  streak: 0,
  totalTimeToday: '0m',

  loadStats: async () => {
    const today = await getTodayStats();
    const hours = Math.floor(today.time_seconds / 3600);
    const minutes = Math.floor((today.time_seconds % 3600) / 60);
    const totalTimeToday = hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
    set({ today, totalTimeToday });
  },

  recordPageRead: async () => {
    await incrementStat('pages_read', 1);
    await get().loadStats();
  },

  recordWordLearned: async () => {
    await incrementStat('words_learned', 1);
    await get().loadStats();
  },

  recordTime: async (seconds) => {
    await incrementStat('time_seconds', seconds);
    await get().loadStats();
  },
}));
