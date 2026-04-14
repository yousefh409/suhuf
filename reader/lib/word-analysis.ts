import type { IrabResult, TranslationResult, AskAiMessage } from '../types';
import { supabase } from './supabase';
import { getDatabase } from './database';
import { hashSentence } from './hash';

const MODEL_VERSION = 'v1';

/** Fetch i'rab analysis. Checks local cache first, then calls Edge Function. */
export async function fetchIrab(word: string, sentence: string, position: number): Promise<IrabResult> {
  const cached = await getCachedIrab(word, sentence);
  if (cached) return cached;

  const { data, error } = await supabase.functions.invoke('irab', {
    body: { word, sentence, position },
  });
  if (error) throw new Error(`I'rab fetch failed: ${error.message}`);

  await cacheIrab(word, sentence, data);
  return data as IrabResult;
}

/** Fetch translation. Checks local cache first, then calls Edge Function. */
export async function fetchTranslation(sentence: string): Promise<TranslationResult> {
  const cached = await getCachedTranslation(sentence);
  if (cached) return cached;

  const { data, error } = await supabase.functions.invoke('translate', {
    body: { sentence },
  });
  if (error) throw new Error(`Translation fetch failed: ${error.message}`);

  await cacheTranslation(sentence, data);
  return data as TranslationResult;
}

/** Send a question to the Ask AI Edge Function. Not cached. */
export async function askAi(
  word: string,
  sentence: string,
  question: string,
  history: AskAiMessage[]
): Promise<string> {
  const { data, error } = await supabase.functions.invoke('ask-ai', {
    body: { word, sentence, question, history },
  });
  if (error) throw new Error(`Ask AI failed: ${error.message}`);
  return data.response as string;
}

// === Cache helpers ===

export async function getCachedIrab(word: string, sentence: string): Promise<IrabResult | null> {
  const db = getDatabase();
  const sentenceHash = await hashSentence(sentence);
  const row = await db.getFirstAsync<{ result_json: string }>(
    'SELECT result_json FROM irab_cache WHERE word = ? AND sentence_hash = ? AND model_version = ?',
    word, sentenceHash, MODEL_VERSION
  );
  return row ? JSON.parse(row.result_json) : null;
}

async function cacheIrab(word: string, sentence: string, result: IrabResult): Promise<void> {
  const db = getDatabase();
  const sentenceHash = await hashSentence(sentence);
  await db.runAsync(
    `INSERT OR REPLACE INTO irab_cache (word, sentence_hash, model_version, result_json, created_at)
     VALUES (?, ?, ?, ?, ?)`,
    word, sentenceHash, MODEL_VERSION, JSON.stringify(result), new Date().toISOString()
  );
}

async function getCachedTranslation(sentence: string): Promise<TranslationResult | null> {
  const db = getDatabase();
  const textHash = await hashSentence(sentence);
  const row = await db.getFirstAsync<{ result_json: string }>(
    'SELECT result_json FROM translation_cache WHERE text_hash = ? AND model_version = ?',
    textHash, MODEL_VERSION
  );
  return row ? JSON.parse(row.result_json) : null;
}

async function cacheTranslation(sentence: string, result: TranslationResult): Promise<void> {
  const db = getDatabase();
  const textHash = await hashSentence(sentence);
  await db.runAsync(
    `INSERT OR REPLACE INTO translation_cache (text_hash, model_version, result_json, created_at)
     VALUES (?, ?, ?, ?)`,
    textHash, MODEL_VERSION, JSON.stringify(result), new Date().toISOString()
  );
}
