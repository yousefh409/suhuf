# Preferences and theming

App-wide user preferences (theme + reading settings) with no-flash rendering and
cross-device sync.

## Model

One typed object, `Preferences` (`web/src/lib/preferences/types.ts`):

| Field | Values | Affects |
|-------|--------|---------|
| theme | paper / sepia / night | whole app |
| textSize | s / m / l / xl | reader |
| arabicFont | scheherazade / amiri / noto-naskh | reader |
| lineSpacing | comfortable / compact | reader |
| tashkeel | boolean (default true) | reader default |

`DEFAULT_PREFERENCES` is the fallback. `parsePreferences` / `coercePreferences`
validate any input field-by-field and fill missing or invalid values from defaults,
so bad data never throws.

## Persistence: cookie first, DB for sync

1. Cookie `suhuf.prefs` (JSON) is the render source of truth. The root layout
   (`web/src/app/layout.tsx`) reads it server-side and stamps `<html>` with
   `data-app-theme`, `data-text-size`, `data-line-spacing`, `data-arabic-font`
   before first paint, so there is no theme flash. Works for signed-out users.
   Reading the cookie opts the app into dynamic rendering.
2. Supabase `user_preferences` (one row per user, owner-only RLS) is the
   cross-device sync layer. Reconciliation rule (`merge.ts`): on load, if a DB row
   exists it wins and is written back to the cookie; if none exists, the cookie
   seeds the DB. Changes write through to both, DB debounced. Last write wins per
   device.

`PreferencesProvider` (client) is seeded from the server-read cookie value, exposes
`usePreferences()` (`prefs` + `setPref`), and on each change updates state, the
cookie, the `<html>` attributes, and (when signed in) the DB via `/api/preferences`.

## CSS: var-backed tokens

Color utilities must resolve through CSS variables for runtime theming. In
`globals.css` the color tokens live in a plain `@theme` block (NOT `@theme inline`):
`@theme inline` bakes literal hex into utilities, which cannot be re-themed at
runtime. The `[data-app-theme="sepia"|"night"]` blocks override the `--color-*`
tokens, so every `bg-parchment` / `text-ink` utility re-themes automatically. paper
is the base default (no override). Opacity utilities like `text-ink/50` re-theme via
the `@supports color-mix(...)` form modern browsers use.

Reading size, line spacing, and Arabic font are driven by `--reading-size`,
`--reading-leading`, and `--font-arabic`, set from the matching `data-*` attributes.

### Scope: app only, not marketing

The theme applies to the product (dashboard, library, reader, settings, login). The
marketing pages (`/` landing, `/welcome`) are designed light with white cards and light
device mockups, so they opt out: their root element carries `data-app-theme="paper"`,
and an explicit `[data-app-theme="paper"]` reset block restores the base palette for
that subtree even when `<html>` is sepia/night. To keep a page light, wrap it the same
way; to theme a new app page, do nothing (it inherits the global theme).

## Reader

The reader shares the one theme system. Its CSS keys off the global `[data-app-theme]`
(not a separate reader attribute), its theme toggle writes the global preference, and
the article reads `--reading-size` / `--reading-leading` / `--font-arabic`. The
in-reader tashkeel toggle is a live per-read override whose default comes from the
preference.

## Adding a preference

1. Add the field + allowed values + default to `types.ts`.
2. Extend `coercePreferences` validation and `serializePreferences`.
3. If it affects rendering before paint, add it to `attributes.ts` and stamp it in
   the root layout; otherwise consume it through `usePreferences()`.
4. Add a control to `web/src/components/settings/SettingsControls.tsx`.
5. Add a column to `user_preferences` (new migration) and map it in
   `web/src/lib/preferences/server.ts`.
