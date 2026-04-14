import * as Crypto from 'expo-crypto';

/** Normalize Arabic text to NFC form for consistent hashing. */
export function normalizeArabic(text: string): string {
  return text.normalize('NFC');
}

/** Hash a sentence using SHA-256 after NFC normalization. Returns hex string. */
export async function hashSentence(sentence: string): Promise<string> {
  const normalized = normalizeArabic(sentence);
  return Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, normalized);
}
