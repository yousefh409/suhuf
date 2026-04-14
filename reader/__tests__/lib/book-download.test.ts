import { downloadBook, isBookDownloaded } from '../../lib/book-download';

jest.mock('../../lib/supabase', () => ({
  fetchBookPages: jest.fn().mockResolvedValue([
    { id: 'p1', book_id: 'b1', page_number: 1, blocks: [{ type: 'prose', tokens: [] }] },
    { id: 'p2', book_id: 'b1', page_number: 2, blocks: [{ type: 'prose', tokens: [] }] },
  ]),
  fetchBookChapters: jest.fn().mockResolvedValue([
    { id: 'c1', book_id: 'b1', title: 'Chapter 1', start_page: 1 },
  ]),
}));

jest.mock('../../lib/database', () => ({
  getDatabase: jest.fn().mockReturnValue({
    getFirstAsync: jest.fn().mockResolvedValue(null),
    runAsync: jest.fn().mockResolvedValue({ lastInsertRowId: 1, changes: 1 }),
  }),
  saveBookLocally: jest.fn().mockResolvedValue(undefined),
  savePages: jest.fn().mockResolvedValue(undefined),
}));

describe('book-download', () => {
  it('downloads book pages and saves to SQLite', async () => {
    const { saveBookLocally, savePages } = require('../../lib/database');
    const book = {
      id: 'b1', openiti_id: 'test', title_ar: 'كتاب', title_en: 'Book',
      author_ar: null, author_en: null, category: 'Nahw', level: 'Beginner',
      cover_color: '#5C4B3A', page_count: 2, content_hash: null,
    };
    await downloadBook(book);
    expect(saveBookLocally).toHaveBeenCalled();
    expect(savePages).toHaveBeenCalled();
  });
});
