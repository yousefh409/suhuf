import { DEFAULT_PREFERENCES, type Preferences } from "./types";

export interface MergeResult {
  effective: Preferences;
  seedDb: boolean;
}

/**
 * Reconcile the local cookie preferences with what is stored in the database.
 *
 * - `db === null` means there is no DB row yet. The cookie becomes effective
 *   and the caller should seed the DB with it (`seedDb: true`).
 * - `db` is a partial object: DB wins for any field it provides; the rest fall
 *   back to DEFAULT_PREFERENCES. `seedDb` is false (row already exists).
 */
export function mergePreferences(
  cookie: Preferences,
  db: Partial<Preferences> | null,
): MergeResult {
  if (db === null) {
    return { effective: { ...cookie }, seedDb: true };
  }

  return { effective: { ...DEFAULT_PREFERENCES, ...db }, seedDb: false };
}
