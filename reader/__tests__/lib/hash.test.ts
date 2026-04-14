import { normalizeArabic, hashSentence } from '../../lib/hash';

describe('hash', () => {
  it('normalizes Arabic text to NFC', () => {
    const nfc = normalizeArabic('كِتَابٌ');
    const nfd = normalizeArabic('كِتَابٌ'.normalize('NFD'));
    expect(nfc).toBe(nfd);
  });

  it('produces consistent hashes for same input', async () => {
    const hash1 = await hashSentence('بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ');
    const hash2 = await hashSentence('بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ');
    expect(hash1).toBe(hash2);
    expect(hash1).toHaveLength(64); // SHA-256 hex
  });

  it('produces different hashes for different input', async () => {
    const hash1 = await hashSentence('الكِتَاب');
    const hash2 = await hashSentence('القَلَم');
    expect(hash1).not.toBe(hash2);
  });
});
