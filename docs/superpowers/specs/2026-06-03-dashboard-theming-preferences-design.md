# Dashboard polish + app-wide theming and preferences

Date: 2026-06-03
Status: Approved, pre-implementation

## Goal

Make the signed-in dashboard and the Discover/library screen look more finished, and
turn two dead controls into real ones. The avatar opens a working profile menu; the
library sort control becomes a proper sort icon. On top of that, ship an app-wide
theming and reading-preferences system with a Settings page that controls it.

## Scope

### Visual polish

- Library sort: replace the native select and the sliders icon with a compact sort
  icon button that opens a parchment-styled dropdown (Relevance / Title / Most popular).
- Remove the dead search icon from the dashboard header. Discover already owns search.
- Replace the flat "Library" dashboard title with a greeting header.
- Avatar opens a working, on-palette profile dropdown.
- Consistent hover, focus, and transition states across header buttons, cards, tabs,
  and links.

### Theming and preferences

- App-wide theme: paper, sepia, night.
- Reading preferences: text size (S/M/L/XL), Arabic font (Scheherazade default, plus
  Amiri and Noto Naskh), line spacing (comfortable/compact), diacritics default.
- Persisted in a cookie plus a Supabase user_preferences table for cross-device sync.
- A Settings page as the single control center.

## Preferences model

One typed preferences object is the source of truth across the app:

| Pref        | Values                                  | Affects               |
|-------------|-----------------------------------------|-----------------------|
| theme       | paper / sepia / night                   | whole app             |
| textSize    | s / m / l / xl                          | reader                |
| arabicFont  | scheherazade / amiri / noto-naskh       | reader                |
| lineSpacing | comfortable / compact                   | reader                |
| tashkeel    | on (default) / off                      | reader default        |

The reader keeps its live in-reader tashkeel toggle as a per-read override; its default
comes from this pref.

## Persistence and no-flash rendering

Two layers.

1. Cookie (`suhuf.prefs`, small JSON). This is the render source of truth. The root
   layout is a server component, so it reads the cookie before first paint and stamps
   the `html` element with data attributes for theme, text size, line spacing, and
   Arabic font, plus the font class. Because the value is read server-side, the first
   HTML is already correct and there is no theme flash. Works for signed-out users too.

2. Supabase user_preferences (one row per user, keyed on the auth user). This is the
   sync layer. Rule, kept simple to avoid conflict math: on load, if a row exists it
   wins and is written back into the cookie; if no row exists, the current cookie seeds
   the row. Every change writes through to both, with the DB write debounced.
   Last write wins per device.

A client PreferencesProvider is seeded from the server-read values and exposes the
prefs plus a setter. On each change it updates state, rewrites the cookie, flips the
html data attributes for instant apply, and syncs the DB when signed in.

## CSS strategy

The app already runs on Tailwind v4, where utility classes like `bg-parchment` resolve
through CSS variables. Theme blocks override the base `--color-*` tokens (so existing
classes restyle automatically) and the reader's `--reader-*` tokens. Text size, line
spacing, and Arabic font are driven by CSS variables set from the html data attributes.

Hard-coded colors that bypass the token system (for example the off-palette zinc in the
existing sign-out button, and any stray emerald or white values) are audited and moved
onto tokens where they affect themed surfaces.

## Reader unification

The reader already renders paper/sepia/night, but through its own localStorage state.
That separate state is retired. The reader inherits the global theme: its themed CSS
selectors point at the global attribute, the in-reader theme toggle writes the global
pref, and the hard-coded reader font size and line height become the textSize and
lineSpacing variables. This keeps one theming system, not two.

The reader's other existing toggles (page markers, hadith cards, diff) stay as they are
and are out of scope.

## Fonts

Amiri and Noto Naskh Arabic are loaded alongside Scheherazade through next/font and
self-hosted. The active Arabic font variable switches on the font data attribute.
Scheherazade stays the default. Tradeoff: two extra Arabic font files, accepted as
brand-appropriate and verified not to bloat load unacceptably.

## UI surfaces

- Profile dropdown (avatar): email header, a three-swatch quick theme switch, a Settings
  link, and sign out. Click-outside to close, parchment-styled.
- Settings page (`/settings`): Appearance (theme swatches, text size, line spacing,
  Arabic font), Reading (diacritics default), and Account (email, sign out).
- Account identity is folded into a Settings section rather than a separate near-empty
  page. The profile menu links Settings plus sign out.
- Sort dropdown, search removal, greeting header, and hover polish as above.

## Routing and gating

`/settings` lives under the signed-in app route group and is added to the protected
prefixes used by the middleware (gating is enforced in both the route-group layout and
the middleware prefix list). Anonymous users on the public landing and library get the
default theme with no switcher in v1; the preferences UI is a signed-in surface.

## To verify, not assume

- Marketing landing in night and sepia. It uses the same tokens, so it would restyle.
  It is tuned for light. Check all three themes there; if a non-default theme looks
  wrong, scope theming to the app, reader, and library and leave the landing fixed.
- Font payload. Confirm the two extra Arabic faces do not bloat load unacceptably.

## Build order

1. Visual polish: sort icon, remove search, greeting, hover states. Independent and
   low-risk.
2. Preferences foundation: cookie, provider, html data attributes, CSS theme blocks,
   applied app-wide.
3. Reader unification onto the global theme and the size/spacing/font variables.
4. Supabase user_preferences table and sync.
5. Profile dropdown and Settings page wiring it all together.

## Out of scope (possible follow-ups)

- In-reader live controls for text size and font (Settings-driven for now; reader
  respects them).
- Anonymous-facing theme switcher.
- Folding the remaining reader toggles (page markers, hadith cards) into Settings.
