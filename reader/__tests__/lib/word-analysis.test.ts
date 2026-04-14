import { fetchIrab, fetchTranslation, getCachedIrab } from '../../lib/word-analysis';

jest.mock('../../lib/supabase', () => ({
  supabase: {
    functions: {
      invoke: jest.fn().mockResolvedValue({
        data: {
          pos: 'noun', role: 'mudaf_ilayh', role_ar: 'مضاف إليه',
          case: 'majrur', case_ar: 'مجرور', marker: 'tanween_kasra',
          marker_ar: 'تنوين كسر', why: 'Test reason', meaning: 'path',
        },
        error: null,
      }),
    },
  },
}));

jest.mock('../../lib/database', () => ({
  getDatabase: jest.fn().mockReturnValue({
    getFirstAsync: jest.fn().mockResolvedValue(null),
    runAsync: jest.fn().mockResolvedValue({ lastInsertRowId: 1, changes: 1 }),
  }),
}));

jest.mock('../../lib/hash', () => ({
  hashSentence: jest.fn().mockResolvedValue('abc123hash'),
}));

describe('word-analysis', () => {
  it('fetches i\'rab from Edge Function when not cached', async () => {
    const result = await fetchIrab('طَرِيقٍ', 'بِكُلِّ طَرِيقٍ', 1);
    expect(result.pos).toBe('noun');
    expect(result.role).toBe('mudaf_ilayh');
  });
});
