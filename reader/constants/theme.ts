// Colors extracted from Paper designs (artboard: Library Main 57Q-1)
export const colors = {
  background: '#F5F0EB',
  card: '#FFFFFF',
  cardBorder: '#E8E0D8',
  primary: '#3D3526',        // Dark brown - buttons, headers
  accent: '#B8860B',         // Gold/amber - progress bars, active states
  textPrimary: '#2C2417',    // Near-black, warm
  textSecondary: '#8A7D6B',  // Muted warm gray
  textTertiary: '#B5A898',   // Lighter muted
  success: '#6B8E4E',        // Completed indicator
  error: '#C45C4A',          // Error states
  white: '#FFFFFF',
} as const;

// Book cover color presets (from Paper designs)
export const coverColors = [
  '#5C4B3A', '#3D3526', '#4A5D4A', '#2E4A4A',
  '#6B5B4A', '#4A3F32', '#5A6B5A', '#3A4A3A',
] as const;

export const fonts = {
  arabic: {
    primary: 'Noto Naskh Arabic',
    amiri: 'Amiri',
    scheherazade: 'Scheherazade New',
  },
  ui: {
    regular: 'DM Sans',
    serif: 'Instrument Serif',
  },
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
  sectionGap: 32,
  screenPadding: 24,
} as const;

export const typography = {
  // UI text (English)
  h1: { fontSize: 28, fontWeight: '700' as const, lineHeight: 34 },
  h2: { fontSize: 22, fontWeight: '600' as const, lineHeight: 28 },
  h3: { fontSize: 18, fontWeight: '600' as const, lineHeight: 24 },
  body: { fontSize: 16, fontWeight: '400' as const, lineHeight: 22 },
  caption: { fontSize: 13, fontWeight: '400' as const, lineHeight: 18 },
  label: { fontSize: 11, fontWeight: '500' as const, lineHeight: 14, letterSpacing: 0.5, textTransform: 'uppercase' as const },
  // Stat numbers
  stat: { fontSize: 36, fontWeight: '700' as const, lineHeight: 42 },
  statLabel: { fontSize: 11, fontWeight: '500' as const, lineHeight: 14, letterSpacing: 0.8, textTransform: 'uppercase' as const },
} as const;

export const borderRadius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  full: 9999,
} as const;
