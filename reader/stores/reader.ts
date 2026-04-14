import { create } from 'zustand';
import type { Page, Chapter, Token, IrabResult, TranslationResult, AskAiMessage } from '../types';
import { getPagesByBook, updateReadingProgress } from '../lib/database';
import { fetchIrab, fetchTranslation, askAi } from '../lib/word-analysis';

interface ReaderState {
  bookId: string | null;
  pages: Page[];
  chapters: Chapter[];
  currentPage: number;
  showTashkeel: boolean;

  selectedToken: Token | null;
  selectedSentence: string | null;
  showWordPopup: boolean;
  wordPopupPosition: { x: number; y: number } | null;

  showWordDetail: boolean;
  activeTab: 'translation' | 'irab' | 'ask-ai';
  irabResult: IrabResult | null;
  translationResult: TranslationResult | null;
  isLoadingAnalysis: boolean;
  analysisError: string | null;

  chatHistory: AskAiMessage[];
  isAiTyping: boolean;

  loadBook: (bookId: string) => Promise<void>;
  goToPage: (page: number) => void;
  toggleTashkeel: () => void;
  selectWord: (token: Token, sentence: string, position: { x: number; y: number }) => void;
  clearSelection: () => void;
  openGrammar: () => Promise<void>;
  openTranslation: () => Promise<void>;
  openAskAi: () => void;
  sendAiQuestion: (question: string) => Promise<void>;
  closeWordDetail: () => void;
}

export const useReaderStore = create<ReaderState>((set, get) => ({
  bookId: null,
  pages: [],
  chapters: [],
  currentPage: 1,
  showTashkeel: true,

  selectedToken: null,
  selectedSentence: null,
  showWordPopup: false,
  wordPopupPosition: null,

  showWordDetail: false,
  activeTab: 'irab',
  irabResult: null,
  translationResult: null,
  isLoadingAnalysis: false,
  analysisError: null,

  chatHistory: [],
  isAiTyping: false,

  loadBook: async (bookId) => {
    try {
      const pages = await getPagesByBook(bookId);
      set({ bookId, pages, currentPage: 1 });
    } catch {
      set({ bookId, pages: [], currentPage: 1 });
    }
  },

  goToPage: (page) => {
    const { bookId, pages } = get();
    if (page >= 1 && page <= pages.length) {
      set({ currentPage: page });
      if (bookId) updateReadingProgress(bookId, page).catch(() => {});
    }
  },

  toggleTashkeel: () => set((s) => ({ showTashkeel: !s.showTashkeel })),

  selectWord: (token, sentence, position) => {
    set({
      selectedToken: token,
      selectedSentence: sentence,
      showWordPopup: true,
      wordPopupPosition: position,
      showWordDetail: false,
    });
  },

  clearSelection: () => {
    set({
      selectedToken: null,
      selectedSentence: null,
      showWordPopup: false,
      wordPopupPosition: null,
    });
  },

  openGrammar: async () => {
    const { selectedToken, selectedSentence } = get();
    if (!selectedToken || !selectedSentence) return;
    set({
      showWordPopup: false,
      showWordDetail: true,
      activeTab: 'irab',
      isLoadingAnalysis: true,
      analysisError: null,
      irabResult: null,
    });
    try {
      const result = await fetchIrab(selectedToken.text, selectedSentence, 0);
      set({ irabResult: result, isLoadingAnalysis: false });
    } catch (e: any) {
      set({ analysisError: e.message, isLoadingAnalysis: false });
    }
  },

  openTranslation: async () => {
    const { selectedSentence } = get();
    if (!selectedSentence) return;
    set({
      showWordPopup: false,
      showWordDetail: true,
      activeTab: 'translation',
      isLoadingAnalysis: true,
      analysisError: null,
      translationResult: null,
    });
    try {
      const result = await fetchTranslation(selectedSentence);
      set({ translationResult: result, isLoadingAnalysis: false });
    } catch (e: any) {
      set({ analysisError: e.message, isLoadingAnalysis: false });
    }
  },

  openAskAi: () => {
    set({
      showWordPopup: false,
      showWordDetail: true,
      activeTab: 'ask-ai',
      chatHistory: [],
    });
  },

  sendAiQuestion: async (question) => {
    const { selectedToken, selectedSentence, chatHistory } = get();
    if (!selectedToken || !selectedSentence) return;
    const newHistory: AskAiMessage[] = [...chatHistory, { role: 'user', content: question }];
    set({ chatHistory: newHistory, isAiTyping: true });
    try {
      const response = await askAi(selectedToken.text, selectedSentence, question, newHistory);
      set({
        chatHistory: [...newHistory, { role: 'assistant', content: response }],
        isAiTyping: false,
      });
    } catch {
      set({
        chatHistory: [...newHistory, { role: 'assistant', content: 'Sorry, something went wrong. Please try again.' }],
        isAiTyping: false,
      });
    }
  },

  closeWordDetail: () => {
    set({
      showWordDetail: false,
      irabResult: null,
      translationResult: null,
      chatHistory: [],
      selectedToken: null,
      selectedSentence: null,
    });
  },
}));
