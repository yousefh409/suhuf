import * as SQLite from 'expo-sqlite';
import { initDatabase, getDownloadedBooks, saveBookLocally, getPagesByBook } from '../../lib/database';

// expo-sqlite mock
jest.mock('expo-sqlite', () => {
  const rows: Record<string, any[]> = {};
  return {
    openDatabaseAsync: jest.fn().mockResolvedValue({
      execAsync: jest.fn().mockImplementation(async (sql: string) => {
        // Track CREATE TABLE calls
      }),
      runAsync: jest.fn().mockImplementation(async (sql: string, ...params: any[]) => {
        return { lastInsertRowId: 1, changes: 1 };
      }),
      getAllAsync: jest.fn().mockResolvedValue([]),
      getFirstAsync: jest.fn().mockResolvedValue(null),
    }),
  };
});

describe('database', () => {
  it('initDatabase opens DB and runs migrations', async () => {
    const db = await initDatabase();
    expect(SQLite.openDatabaseAsync).toHaveBeenCalledWith('suhuf.db');
    expect(db.execAsync).toHaveBeenCalled();
  });
});
