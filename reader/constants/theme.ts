// Colors extracted from Paper designs (artboard: Library Main — Mobile DNC-0)
export const colors = {
  background: '#F5F0EB',
  card: '#FFFFFF',
  cardBorder: '#E8E0D8',
  primary: '#3D3526',        // Dark brown — buttons, headers
  accent: '#B8860B',         // Gold/amber — progress bars, active states
  textPrimary: '#1A1208',    // Near-black, warm (was #2C2417)
  textSecondary: '#8B7355',  // Warm medium brown (was #8A7D6B)
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
    serif: 'Cormorant Garamond',
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
  screenPadding: 20,
} as const;

export const typography = {
  h1: { fontSize: 24, fontWeight: '700' as const, lineHeight: 30 },
  h2: { fontSize: 18, fontWeight: '600' as const, lineHeight: 24 },
  h3: { fontSize: 16, fontWeight: '600' as const, lineHeight: 22 },
  body: { fontSize: 15, fontWeight: '400' as const, lineHeight: 22 },
  caption: { fontSize: 13, fontWeight: '400' as const, lineHeight: 18 },
  label: { fontSize: 11, fontWeight: '500' as const, lineHeight: 14, letterSpacing: 0.5, textTransform: 'uppercase' as const },
  stat: { fontSize: 26, fontWeight: '700' as const, lineHeight: 32 },
  statLabel: { fontSize: 10, fontWeight: '500' as const, lineHeight: 13, letterSpacing: 0.4, textTransform: 'uppercase' as const },
  sectionTitle: { fontSize: 16, fontWeight: '600' as const, lineHeight: 22 },
} as const;

export const borderRadius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  full: 9999,
} as const;
