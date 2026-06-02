export type IrabRequest = { word: string; sentence: string; position: number };
export type IrabResult = {
  pos: string;
  role: string;
  role_ar: string;
  case: string;
  case_ar: string;
  marker: string;
  marker_ar: string;
  why: string;
  meaning: string;
};

export type TranslateRequest = { sentence: string };
export type RelatedWord = { word: string; root: string; meaning: string };
export type TranslateResult = { translation: string; related_words: RelatedWord[] };

export type ChatTurn = { role: "user" | "assistant"; content: string };
export type AskAiRequest = {
  word: string;
  sentence: string;
  question: string;
  history?: ChatTurn[];
};
export type AskAiResult = { response: string };
