import { create } from 'zustand';
import type { Settings, ArabicFont, AiLanguage, GrammarDetail } from '../types';

interface SettingsState extends Settings {
  setFontSize: (size: number) => void;
  setArabicFont: (font: ArabicFont) => void;
  setAiLanguage: (lang: AiLanguage) => void;
  setGrammarDetail: (level: GrammarDetail) => void;
  toggleTashkeel: () => void;
  toggleNotifications: () => void;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  fontSize: 24,
  arabicFont: 'Noto Naskh Arabic',
  aiLanguage: 'English',
  grammarDetail: 'Detailed',
  showTashkeel: true,
  notificationsEnabled: true,

  setFontSize: (fontSize) => set({ fontSize }),
  setArabicFont: (arabicFont) => set({ arabicFont }),
  setAiLanguage: (aiLanguage) => set({ aiLanguage }),
  setGrammarDetail: (grammarDetail) => set({ grammarDetail }),
  toggleTashkeel: () => set((s) => ({ showTashkeel: !s.showTashkeel })),
  toggleNotifications: () => set((s) => ({ notificationsEnabled: !s.notificationsEnabled })),
}));
