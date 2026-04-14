# Reader App UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul the reader app's UI to match the Paper design exactly -- fonts, colors, icons, spacing, and layout for every screen.

**Architecture:** Update the design token foundation (theme.ts), add an icon system (@expo/vector-icons + Feather set), load the Cormorant Garamond serif font, then update each screen/component to match the Paper designs. Profile and Settings are full rewrites. All other screens get targeted style and icon updates.

**Tech Stack:** Expo SDK 54, React Native, @expo/vector-icons (Feather), @expo-google-fonts/cormorant-garamond, existing Zustand stores.

---

## File Map

### New files
- `reader/components/ui/Icon.tsx` -- Thin wrapper around Feather icons with theme-aware defaults

### Modified files
- `reader/package.json` -- Add @expo/vector-icons, @expo-google-fonts/cormorant-garamond
- `reader/constants/theme.ts` -- Updated colors, typography, font references
- `reader/app/_layout.tsx` -- Load CormorantGaramond fonts
- `reader/components/ui/Header.tsx` -- Serif title, icon back button, flexible right slot
- `reader/components/library/StatsRow.tsx` -- 2x2 grid on mobile, corrected font sizes
- `reader/components/library/ContinueReading.tsx` -- Remove category tag, match Paper layout
- `reader/components/library/FilteredTabs.tsx` -- Simplified dot+text pills, "Full Library" pill button
- `reader/components/library/BookCard.tsx` -- Minor font size tweaks
- `reader/components/library/CategoryPills.tsx` -- Counts inside pills
- `reader/app/index.tsx` -- Feather search icon, serif section titles, proper avatar
- `reader/app/discover.tsx` -- Search bar icon, sort button icon, result text format
- `reader/app/book/[id].tsx` -- Richer header with title/subtitle, bookmark/menu icons, bottom bar
- `reader/components/reader/WordPopup.tsx` -- Feather icons replacing unicode
- `reader/components/reader/TashkeelToggle.tsx` -- Eye icon replacing emoji
- `reader/components/word-detail/WordDetailSheet.tsx` -- Underlined tab bar, word header with large arabic + transliteration
- `reader/components/word-detail/TranslationTab.tsx` -- MEANING / ROOT+PATTERN / IN THIS SENTENCE / FROM THE SAME ROOT sections
- `reader/components/word-detail/IrabTab.tsx` -- TYPE+CASE side-by-side, ROLE, MARKER, WHY THIS CASE sections
- `reader/components/word-detail/AskAiTab.tsx` -- Suggestion chips match design, send arrow icon
- `reader/app/profile.tsx` -- Full rewrite: subscription, account, support sections, sign out
- `reader/app/settings.tsx` -- Full rewrite: icon+label+value+chevron rows, toggle switch

---

### Task 1: Install Dependencies

**Files:**
- Modify: `reader/package.json`

- [ ] **Step 1: Install @expo/vector-icons and Cormorant Garamond font**

```bash
cd reader && npx expo install @expo/vector-icons @expo-google-fonts/cormorant-garamond
```

- [ ] **Step 2: Verify installation**

```bash
cd reader && node -e "require.resolve('@expo/vector-icons'); console.log('vector-icons OK')" && node -e "require.resolve('@expo-google-fonts/cormorant-garamond'); console.log('cormorant OK')"
```

Expected: Both print OK.

- [ ] **Step 3: Commit**

```bash
git add reader/package.json reader/package-lock.json
git commit -m "chore(reader): add @expo/vector-icons and cormorant-garamond font"
```

---

### Task 2: Update Theme Tokens

**Files:**
- Modify: `reader/constants/theme.ts`

- [ ] **Step 1: Update theme.ts**

Replace the entire file with corrected values extracted from Paper designs:

```ts
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
    serif: 'Cormorant Garamond',  // was Instrument Serif
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
  screenPadding: 20,  // was 24, tighter on mobile
} as const;

export const typography = {
  // UI text (English)
  h1: { fontSize: 24, fontWeight: '700' as const, lineHeight: 30 },
  h2: { fontSize: 18, fontWeight: '600' as const, lineHeight: 24 },
  h3: { fontSize: 16, fontWeight: '600' as const, lineHeight: 22 },
  body: { fontSize: 15, fontWeight: '400' as const, lineHeight: 22 },
  caption: { fontSize: 13, fontWeight: '400' as const, lineHeight: 18 },
  label: { fontSize: 11, fontWeight: '500' as const, lineHeight: 14, letterSpacing: 0.5, textTransform: 'uppercase' as const },
  // Stat numbers
  stat: { fontSize: 26, fontWeight: '700' as const, lineHeight: 32 },
  statLabel: { fontSize: 10, fontWeight: '500' as const, lineHeight: 13, letterSpacing: 0.4, textTransform: 'uppercase' as const },
  // Section title (serif)
  sectionTitle: { fontSize: 16, fontWeight: '600' as const, lineHeight: 22 },
} as const;

export const borderRadius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  full: 9999,
} as const;
```

Key changes from current:
- `textPrimary`: `#2C2417` -> `#1A1208` (darker)
- `textSecondary`: `#8A7D6B` -> `#8B7355` (warmer brown)
- `fonts.ui.serif`: `Instrument Serif` -> `Cormorant Garamond`
- `spacing.screenPadding`: `24` -> `20` (tighter mobile)
- `typography.h1.fontSize`: `28` -> `24`
- `typography.stat.fontSize`: `36` -> `26`
- `typography.statLabel.fontSize`: `11` -> `10`, letterSpacing `0.8` -> `0.4`
- Added `typography.sectionTitle` for serif section headers

- [ ] **Step 2: Commit**

```bash
git add reader/constants/theme.ts
git commit -m "style(reader): update theme tokens to match Paper designs"
```

---

### Task 3: Load Cormorant Garamond Font

**Files:**
- Modify: `reader/app/_layout.tsx`

- [ ] **Step 1: Add Cormorant Garamond to font loading**

Add these two entries to the `useFonts` call:

```ts
'CormorantGaramond': require('@expo-google-fonts/cormorant-garamond/400Regular/CormorantGaramond_400Regular.ttf'),
'CormorantGaramond-SemiBold': require('@expo-google-fonts/cormorant-garamond/600SemiBold/CormorantGaramond_600SemiBold.ttf'),
```

- [ ] **Step 2: Verify the require paths exist**

```bash
cd reader && ls node_modules/@expo-google-fonts/cormorant-garamond/
```

Adjust paths if the directory structure differs (check for `CormorantGaramond_400Regular.ttf` vs alternate naming).

- [ ] **Step 3: Commit**

```bash
git add reader/app/_layout.tsx
git commit -m "feat(reader): load Cormorant Garamond serif font"
```

---

### Task 4: Create Icon Component

**Files:**
- Create: `reader/components/ui/Icon.tsx`

- [ ] **Step 1: Create the Icon wrapper**

```tsx
import { Feather } from '@expo/vector-icons';
import { colors } from '../../constants/theme';

export type IconName = React.ComponentProps<typeof Feather>['name'];

interface IconProps {
  name: IconName;
  size?: number;
  color?: string;
}

export function Icon({ name, size = 20, color = colors.textPrimary }: IconProps) {
  return <Feather name={name} size={size} color={color} />;
}
```

- [ ] **Step 2: Commit**

```bash
git add reader/components/ui/Icon.tsx
git commit -m "feat(reader): add Feather icon wrapper component"
```

---

### Task 5: Update Header Component

**Files:**
- Modify: `reader/components/ui/Header.tsx`

- [ ] **Step 1: Rewrite Header.tsx**

The Paper design shows:
- Non-back mode: Serif title ("Library") left-aligned + right slot
- Back mode: Chevron icon + "Library" text left, centered title, right slot
- Settings/Profile back mode: Chevron + "Profile" left, "Settings" centered

```tsx
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { Icon } from './Icon';
import { colors, typography, spacing } from '../../constants/theme';

interface HeaderProps {
  title: string;
  showBack?: boolean;
  backLabel?: string;
  subtitle?: string;
  rightContent?: React.ReactNode;
}

export function Header({ title, showBack, backLabel = 'Library', subtitle, rightContent }: HeaderProps) {
  const router = useRouter();
  return (
    <View style={styles.container}>
      <View style={styles.left}>
        {showBack ? (
          <Pressable onPress={() => router.back()} style={styles.backButton} hitSlop={8}>
            <Icon name="chevron-left" size={22} color={colors.textSecondary} />
            <Text style={styles.backText}>{backLabel}</Text>
          </Pressable>
        ) : (
          <Text style={styles.title}>{title}</Text>
        )}
      </View>
      {showBack && (
        <View style={styles.center}>
          <Text style={styles.centerTitle}>{title}</Text>
          {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
        </View>
      )}
      <View style={styles.right}>{rightContent}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.screenPadding,
    paddingVertical: spacing.md,
    backgroundColor: colors.background,
  },
  left: { flex: 1, alignItems: 'flex-start' },
  center: { flex: 2, alignItems: 'center' },
  right: { flex: 1, alignItems: 'flex-end', flexDirection: 'row', justifyContent: 'flex-end', gap: spacing.sm },
  title: {
    fontFamily: 'CormorantGaramond-SemiBold',
    fontSize: 24,
    color: colors.textPrimary,
    lineHeight: 30,
  },
  centerTitle: {
    fontFamily: 'DMSans-SemiBold',
    fontSize: 16,
    color: colors.textPrimary,
    lineHeight: 22,
  },
  subtitle: {
    fontFamily: 'DMSans',
    fontSize: 12,
    color: colors.textSecondary,
    lineHeight: 16,
  },
  backButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    paddingVertical: spacing.xs,
  },
  backText: {
    fontFamily: 'DMSans',
    fontSize: 15,
    color: colors.textSecondary,
  },
});
```

- [ ] **Step 2: Commit**

```bash
git add reader/components/ui/Header.tsx
git commit -m "style(reader): update Header with serif title and icon back button"
```

---

### Task 6: Update StatsRow (2x2 Grid)

**Files:**
- Modify: `reader/components/library/StatsRow.tsx`

- [ ] **Step 1: Rewrite StatsRow.tsx**

Paper mobile design shows a 2x2 grid (2 cards per row), center-aligned text, with the stat value and unit on the same baseline.

```tsx
import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing, borderRadius, typography } from '../../constants/theme';

interface StatCardProps {
  label: string;
  value: string | number;
  unit?: string;
}

function StatCard({ label, value, unit }: StatCardProps) {
  return (
    <View style={styles.card}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.valueRow}>
        <Text style={styles.value}>{value}</Text>
        {unit ? <Text style={styles.unit}> {unit}</Text> : null}
      </View>
    </View>
  );
}

interface StatsRowProps {
  pagesToday: number;
  wordsLearned: number;
  streak: number;
  timeRead: string;
}

export function StatsRow({ pagesToday, wordsLearned, streak, timeRead }: StatsRowProps) {
  return (
    <View style={styles.grid}>
      <View style={styles.row}>
        <StatCard label="TODAY" value={pagesToday} unit="pages" />
        <StatCard label="WORDS LEARNED" value={wordsLearned} unit="this week" />
      </View>
      <View style={styles.row}>
        <StatCard label="STREAK" value={streak} unit="days" />
        <StatCard label="TIME READ" value={timeRead} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    paddingHorizontal: spacing.screenPadding,
    gap: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  card: {
    flex: 1,
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    alignItems: 'center',
  },
  label: {
    ...typography.statLabel,
    fontFamily: 'DMSans-Medium',
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  valueRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  value: {
    ...typography.stat,
    fontFamily: 'DMSans-Bold',
    color: colors.textPrimary,
  },
  unit: {
    fontSize: 12,
    fontFamily: 'DMSans',
    color: colors.textSecondary,
  },
});
```

- [ ] **Step 2: Commit**

```bash
git add reader/components/library/StatsRow.tsx
git commit -m "style(reader): update StatsRow to 2x2 grid matching Paper design"
```

---

### Task 7: Update ContinueReading

**Files:**
- Modify: `reader/components/library/ContinueReading.tsx`

- [ ] **Step 1: Update ContinueReading.tsx**

Paper design shows: cover thumbnail, title (bold), author + category on same line separated by " . ", progress bar with percentage, Resume button (first card only). No separate category pill tag.

Replace the `categoryTag` and `categoryText` styles and the `<View style={styles.categoryTag}>` block. Change the author line to include category:

In the BookRow component, replace the author + category tag section:

```tsx
<Text style={styles.author} numberOfLines={1}>
  {book.author_en ?? book.author_ar} · {book.category}
</Text>
```

Remove the `categoryTag` and `categoryText` from the styles. Remove the separate `<View style={styles.categoryTag}>` JSX block.

Also update `bookTitle` font:
```ts
bookTitle: {
  fontFamily: 'DMSans-SemiBold',
  fontSize: 16,
  color: colors.textPrimary,
  lineHeight: 22,
},
```

- [ ] **Step 2: Commit**

```bash
git add reader/components/library/ContinueReading.tsx
git commit -m "style(reader): update ContinueReading to match Paper design"
```

---

### Task 8: Update FilteredTabs

**Files:**
- Modify: `reader/components/library/FilteredTabs.tsx`

- [ ] **Step 1: Update FilteredTabs.tsx**

Paper mobile design shows:
- Tab pills: dot + label + count, no background on inactive (just text), active has no background pill
- "Full Library" is a pill button with arrow, aligned right
- Remove the "Completed" tab (Paper only shows "In Progress" and "Saved")

Actually, looking at the Paper mobile design more closely, the tabs are simple inline text: `[dot] In Progress 5  [dot] Saved 18` without pill backgrounds on inactive. The active one is bold. The "Full Library ->" is a separate pill button on the right.

Update the pill styles: inactive has no background, just text. Remove `pillActive` background. Make active text bold. Keep the dot. Update "Full Library" to be a pill with border.

Key style changes:
```ts
pill: {
  flexDirection: 'row',
  alignItems: 'center',
  gap: spacing.xs,
  paddingHorizontal: spacing.sm,
  paddingVertical: spacing.xs,
},
// Remove pillActive background
pillText: {
  fontFamily: 'DMSans-Medium',
  fontSize: 14,
  color: colors.textSecondary,
},
pillTextActive: {
  fontFamily: 'DMSans-Bold',
  color: colors.textPrimary,
},
pillCount: {
  fontSize: 13,
  fontFamily: 'DMSans',
  color: colors.textTertiary,
},
fullLibraryBtn: {
  marginLeft: 'auto',
  flexDirection: 'row',
  alignItems: 'center',
  gap: spacing.xs,
  backgroundColor: colors.primary,
  borderRadius: borderRadius.full,
  paddingHorizontal: spacing.md,
  paddingVertical: spacing.sm,
},
fullLibraryText: {
  fontSize: 13,
  fontFamily: 'DMSans-SemiBold',
  color: colors.white,
},
```

Also add an arrow icon to the Full Library button:
```tsx
import { Icon } from '../ui/Icon';

// In JSX:
<Pressable onPress={() => router.push('/discover')} style={styles.fullLibraryBtn}>
  <Text style={styles.fullLibraryText}>Full Library</Text>
  <Icon name="arrow-right" size={14} color={colors.white} />
</Pressable>
```

- [ ] **Step 2: Commit**

```bash
git add reader/components/library/FilteredTabs.tsx
git commit -m "style(reader): update FilteredTabs to match Paper design"
```

---

### Task 9: Update Library Main Screen

**Files:**
- Modify: `reader/app/index.tsx`

- [ ] **Step 1: Update index.tsx**

Changes needed:
1. Replace unicode search `⌕` with Feather search icon
2. Update avatar to show "YH" (two initials) and link to profile
3. Section titles use Cormorant Garamond serif font
4. Remove "Your Books" section title (Paper design doesn't have it)

```tsx
import { Icon } from '../components/ui/Icon';
import { useRouter } from 'expo-router';

function SearchIcon() {
  return (
    <Pressable style={headerIconStyles.btn} hitSlop={8}>
      <Icon name="search" size={20} color={colors.textPrimary} />
    </Pressable>
  );
}

function ProfileAvatar() {
  const router = useRouter();
  return (
    <Pressable onPress={() => router.push('/profile')}>
      <View style={headerIconStyles.avatar}>
        <Text style={headerIconStyles.avatarText}>YH</Text>
      </View>
    </Pressable>
  );
}
```

Update section title style to use serif:
```ts
sectionTitle: {
  fontFamily: 'CormorantGaramond-SemiBold',
  ...typography.sectionTitle,
  color: colors.textPrimary,
},
```

Remove the "Your Books" section header wrapping `FilteredTabs`. The Paper design shows the tab pills directly without a section title.

- [ ] **Step 2: Commit**

```bash
git add reader/app/index.tsx
git commit -m "style(reader): update Library Main with icons and serif titles"
```

---

### Task 10: Update Discover Screen

**Files:**
- Modify: `reader/app/discover.tsx`

- [ ] **Step 1: Update discover.tsx**

Changes:
1. Add search icon inside the search bar (left side)
2. Update sort button to use Feather icon
3. Update result text format: "Nahw . 1,240 texts" (category + count)
4. Update search placeholder to "Search 10,247 Arabic texts..."

```tsx
import { Icon } from '../components/ui/Icon';

// Search bar with icon:
<View style={styles.searchContainer}>
  <View style={styles.searchBar}>
    <Icon name="search" size={18} color={colors.textTertiary} />
    <TextInput
      style={styles.searchInput}
      placeholder={`Search ${catalog.length.toLocaleString()} Arabic texts...`}
      placeholderTextColor={colors.textTertiary}
      value={query}
      onChangeText={handleSearch}
      returnKeyType="search"
      autoCorrect={false}
    />
  </View>
</View>

// Sort button with icon:
<Pressable style={styles.sortButton}>
  <Icon name="sliders" size={16} color={colors.textPrimary} />
  <Text style={styles.sortText}>Sort</Text>
</Pressable>

// Result text:
<Text style={styles.resultCount}>
  {selectedCategory ? `${selectedCategory} · ` : ''}{catalog.length.toLocaleString()} texts
</Text>
```

Update styles for searchBar:
```ts
searchBar: {
  flexDirection: 'row',
  alignItems: 'center',
  backgroundColor: colors.card,
  borderRadius: borderRadius.lg,
  borderWidth: 1,
  borderColor: colors.cardBorder,
  paddingHorizontal: spacing.md,
  gap: spacing.sm,
},
searchInput: {
  flex: 1,
  paddingVertical: spacing.md,
  fontSize: 15,
  fontFamily: 'DMSans',
  color: colors.textPrimary,
},
sortButton: {
  flexDirection: 'row',
  alignItems: 'center',
  gap: spacing.xs,
  backgroundColor: colors.card,
  borderRadius: borderRadius.md,
  borderWidth: 1,
  borderColor: colors.cardBorder,
  paddingHorizontal: spacing.md,
  paddingVertical: spacing.sm,
},
```

- [ ] **Step 2: Commit**

```bash
git add reader/app/discover.tsx
git commit -m "style(reader): update Discover with search icon and sort icon"
```

---

### Task 11: Update Reading Session

**Files:**
- Modify: `reader/app/book/[id].tsx`

- [ ] **Step 1: Update book/[id].tsx**

Paper design shows:
- Header: `< Library` back (chevron icon + text), centered book title + chapter subtitle, bookmark icon + menu icon on right
- Bottom bar: Tashkeel toggle pill (eye icon), "Recording" indicator with red dot, "2 errors" text, "Stop" pill button with square icon, OR "Start" pill button with play icon
- Page number: `3 / 14` left-aligned

Add right header content:
```tsx
<Header
  title="Reading"
  showBack
  rightContent={
    <>
      <Pressable hitSlop={8}>
        <Icon name="bookmark" size={22} color={colors.textPrimary} />
      </Pressable>
      <Pressable hitSlop={8}>
        <Icon name="more-vertical" size={22} color={colors.textPrimary} />
      </Pressable>
    </>
  }
/>
```

Update footer to include recording controls:
```tsx
<View style={styles.footer}>
  <TashkeelToggle />
  <Text style={styles.pageNumber}>
    {currentPage} / {pages.length || '\u2014'}
  </Text>
  <Pressable style={styles.startButton}>
    <Icon name="play" size={14} color={colors.white} />
    <Text style={styles.startText}>Start</Text>
  </Pressable>
</View>
```

Add styles for the start button:
```ts
startButton: {
  flexDirection: 'row',
  alignItems: 'center',
  gap: spacing.xs,
  backgroundColor: colors.primary,
  borderRadius: borderRadius.full,
  paddingHorizontal: spacing.md,
  paddingVertical: spacing.sm,
},
startText: {
  fontFamily: 'DMSans-SemiBold',
  fontSize: 13,
  color: colors.white,
},
```

- [ ] **Step 2: Commit**

```bash
git add reader/app/book/\\[id\\].tsx
git commit -m "style(reader): update Reading Session with icons and controls"
```

---

### Task 12: Update WordPopup

**Files:**
- Modify: `reader/components/reader/WordPopup.tsx`

- [ ] **Step 1: Replace unicode icons with Feather icons**

```tsx
import { Icon } from '../ui/Icon';

// Replace ✏ with:
<Icon name="edit-2" size={14} color={colors.white} />

// Replace ⟳ with:
<Icon name="globe" size={14} color={colors.white} />

// Replace ✕ with:
<Icon name="copy" size={14} color={colors.white} />
```

Also add a "Copy" text label to the third button to match the Paper design (which shows Grammar, Translate, Copy icons):

```tsx
<Pressable style={styles.button} onPress={clearSelection}>
  <Icon name="copy" size={14} color={colors.white} />
</Pressable>
```

- [ ] **Step 2: Commit**

```bash
git add reader/components/reader/WordPopup.tsx
git commit -m "style(reader): replace unicode icons in WordPopup with Feather"
```

---

### Task 13: Update TashkeelToggle

**Files:**
- Modify: `reader/components/reader/TashkeelToggle.tsx`

- [ ] **Step 1: Replace emoji with Feather eye icon**

```tsx
import { Icon } from '../ui/Icon';

// Replace the emoji Text with:
<Icon
  name={showTashkeel ? 'eye' : 'eye-off'}
  size={16}
  color={showTashkeel ? colors.white : colors.textSecondary}
/>
```

Remove the icon/iconActive styles (no longer needed for Text).

- [ ] **Step 2: Commit**

```bash
git add reader/components/reader/TashkeelToggle.tsx
git commit -m "style(reader): replace emoji with eye icon in TashkeelToggle"
```

---

### Task 14: Update WordDetailSheet

**Files:**
- Modify: `reader/components/word-detail/WordDetailSheet.tsx`

- [ ] **Step 1: Update WordDetailSheet.tsx**

Paper design shows:
- Large Arabic word centered with transliteration below
- Underlined tab bar (not pill tabs): "Translation" | "I3rab" with active underline
- Remove the "Ask AI" tab from the tab bar (it's accessible via "+ Ask AI" button in header)

Tab labels change: `Translate` -> `Translation`, `Grammar` -> `I3rab`, remove `Ask AI`.

Update tab bar styles to use underline instead of pills:
```ts
tabBar: {
  flexDirection: 'row',
  borderBottomWidth: 1,
  borderBottomColor: colors.cardBorder,
  marginBottom: spacing.md,
},
tab: {
  flex: 1,
  alignItems: 'center',
  paddingVertical: spacing.sm,
},
tabActive: {
  borderBottomWidth: 2,
  borderBottomColor: colors.accent,
},
tabText: {
  fontFamily: 'DMSans',
  fontSize: 15,
  color: colors.textTertiary,
},
tabTextActive: {
  fontFamily: 'DMSans-SemiBold',
  color: colors.textPrimary,
},
```

Update the word header to show larger centered Arabic with transliteration:
```ts
wordHeader: {
  alignItems: 'center',
  paddingVertical: spacing.lg,
  gap: spacing.xs,
},
wordArabic: {
  fontFamily: 'NotoNaskhArabic-Bold',
  fontSize: 48,
  color: colors.textPrimary,
  textAlign: 'center',
},
wordTransliteration: {
  fontFamily: 'DMSans',
  fontSize: 14,
  color: colors.textTertiary,
  textAlign: 'center',
},
```

Replace the back arrow `‹` with:
```tsx
<Icon name="chevron-left" size={24} color={colors.textSecondary} />
```

Update TABS array to only `['translation', 'irab']` and update TAB_LABELS:
```ts
const TAB_LABELS: Record<Tab, string> = {
  translation: 'Translation',
  irab: 'I3rab',
};
```

- [ ] **Step 2: Commit**

```bash
git add reader/components/word-detail/WordDetailSheet.tsx
git commit -m "style(reader): update WordDetailSheet with underlined tabs and centered word"
```

---

### Task 15: Update TranslationTab

**Files:**
- Modify: `reader/components/word-detail/TranslationTab.tsx`

- [ ] **Step 1: Update TranslationTab.tsx**

Paper design shows sections: MEANING, ROOT + PATTERN side-by-side, IN THIS SENTENCE, FROM THE SAME ROOT (as pills), and "Ask AI to learn more" button at bottom.

Restructure the component layout:
```tsx
<ScrollView style={styles.scroll} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
  {/* MEANING */}
  <View style={styles.section}>
    <Text style={styles.sectionLabel}>MEANING</Text>
    <Text style={styles.meaningText}>{translationResult.translation}</Text>
  </View>

  {/* ROOT + PATTERN side by side */}
  <View style={styles.twoCol}>
    <View style={styles.col}>
      <Text style={styles.sectionLabel}>ROOT</Text>
      {translationResult.related_words.length > 0 && (
        <>
          <Text style={styles.arabicValue}>{translationResult.related_words[0].root}</Text>
          <Text style={styles.arabicCaption}>to knock, to tread</Text>
        </>
      )}
    </View>
    <View style={styles.col}>
      <Text style={styles.sectionLabel}>PATTERN</Text>
      <Text style={styles.arabicValue}>{'\u0641\u0639\u064A\u0644'}</Text>
    </View>
  </View>

  {/* IN THIS SENTENCE */}
  <View style={styles.section}>
    <Text style={styles.sectionLabel}>IN THIS SENTENCE</Text>
    <Text style={styles.sentenceText}>"Every path" — referring to each avenue of sin and desire...</Text>
  </View>

  {/* FROM THE SAME ROOT */}
  {translationResult.related_words.length > 0 && (
    <View style={styles.section}>
      <Text style={styles.sectionLabel}>FROM THE SAME ROOT</Text>
      <View style={styles.pillsRow}>
        {translationResult.related_words.map((rw, i) => (
          <View key={i} style={styles.relatedPill}>
            <Text style={styles.relatedPillArabic}>{rw.word}</Text>
            <Text style={styles.relatedPillMeaning}>{rw.meaning}</Text>
          </View>
        ))}
      </View>
    </View>
  )}

  {/* Ask AI button */}
  <Pressable style={styles.askAiButton} onPress={openAskAi}>
    <Text style={styles.askAiIcon}>+</Text>
    <Text style={styles.askAiText}>Ask AI to learn more</Text>
  </Pressable>
</ScrollView>
```

Add new styles:
```ts
twoCol: { flexDirection: 'row', gap: spacing.lg },
col: { flex: 1, gap: spacing.xs },
arabicValue: { fontFamily: 'NotoNaskhArabic', fontSize: 20, color: colors.textPrimary, writingDirection: 'rtl' },
arabicCaption: { fontFamily: 'DMSans', fontSize: 12, color: colors.textSecondary },
sentenceText: { fontFamily: 'DMSans', fontSize: 15, color: colors.textPrimary, lineHeight: 24 },
pillsRow: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
relatedPill: {
  flexDirection: 'row', gap: spacing.xs, alignItems: 'center',
  backgroundColor: colors.background, borderRadius: borderRadius.full,
  paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
},
relatedPillArabic: { fontFamily: 'NotoNaskhArabic', fontSize: 16, color: colors.textPrimary },
relatedPillMeaning: { fontFamily: 'DMSans', fontSize: 13, color: colors.textSecondary },
askAiButton: {
  flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: spacing.sm,
  backgroundColor: '#F5EDD0', borderRadius: borderRadius.md,
  paddingVertical: spacing.md, marginTop: spacing.md,
},
askAiIcon: { fontFamily: 'DMSans-Bold', fontSize: 18, color: colors.accent },
askAiText: { fontFamily: 'DMSans-SemiBold', fontSize: 15, color: colors.textPrimary },
```

- [ ] **Step 2: Commit**

```bash
git add reader/components/word-detail/TranslationTab.tsx
git commit -m "style(reader): update TranslationTab layout to match Paper design"
```

---

### Task 16: Update IrabTab

**Files:**
- Modify: `reader/components/word-detail/IrabTab.tsx`

- [ ] **Step 1: Update IrabTab.tsx**

Paper design shows: TYPE + CASE side-by-side (label above, arabic value below with english), ROLE section, MARKER section, WHY THIS CASE? section, "Ask AI to learn more" button.

Replace the current card/tag layout with side-by-side sections:

```tsx
<ScrollView style={styles.scroll} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
  {/* TYPE + CASE side by side */}
  <View style={styles.twoCol}>
    <View style={styles.col}>
      <Text style={styles.sectionLabel}>TYPE</Text>
      <Text style={styles.arabicValue}>{irabResult.pos_ar ?? irabResult.pos}</Text>
      <Text style={styles.englishValue}>{irabResult.pos}</Text>
    </View>
    {irabResult.case && (
      <View style={styles.col}>
        <Text style={styles.sectionLabel}>CASE</Text>
        <Text style={styles.arabicValue}>{irabResult.case_ar ?? irabResult.case}</Text>
        <Text style={styles.englishValue}>{irabResult.case}</Text>
      </View>
    )}
  </View>

  {/* ROLE */}
  {irabResult.role && (
    <View style={styles.section}>
      <Text style={styles.sectionLabel}>ROLE</Text>
      <Text style={styles.arabicValue}>{irabResult.role_ar ?? irabResult.role}</Text>
      <Text style={styles.englishValue}>{irabResult.role}</Text>
    </View>
  )}

  {/* MARKER */}
  {irabResult.marker && (
    <View style={styles.section}>
      <Text style={styles.sectionLabel}>MARKER</Text>
      <Text style={styles.arabicValue}>{irabResult.marker_ar ?? irabResult.marker}</Text>
      <Text style={styles.englishValue}>{irabResult.marker}</Text>
    </View>
  )}

  {/* WHY THIS CASE? */}
  {irabResult.why && (
    <View style={styles.whyCard}>
      <Text style={styles.sectionLabel}>WHY THIS CASE?</Text>
      <Text style={styles.whyText}>{irabResult.why}</Text>
    </View>
  )}

  {/* Ask AI button */}
  <Pressable style={styles.askAiButton} onPress={openAskAi}>
    <Text style={styles.askAiIcon}>+</Text>
    <Text style={styles.askAiText}>Ask AI to learn more</Text>
  </Pressable>
</ScrollView>
```

Update styles:
```ts
section: { gap: spacing.xs },
sectionLabel: { fontFamily: 'DMSans-Medium', ...typography.label, color: colors.textTertiary },
twoCol: { flexDirection: 'row', gap: spacing.lg },
col: { flex: 1, gap: spacing.xs },
arabicValue: { fontFamily: 'NotoNaskhArabic', fontSize: 22, color: colors.textPrimary, writingDirection: 'rtl' },
englishValue: { fontFamily: 'DMSans', fontSize: 13, color: colors.textSecondary },
whyCard: {
  backgroundColor: '#F5EDD0', borderRadius: borderRadius.md,
  padding: spacing.md, gap: spacing.sm,
},
whyText: { fontFamily: 'DMSans', fontSize: 15, color: colors.textPrimary, lineHeight: 24 },
askAiButton: {
  flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: spacing.sm,
  backgroundColor: '#F5EDD0', borderRadius: borderRadius.md,
  paddingVertical: spacing.md, marginTop: spacing.md,
},
askAiIcon: { fontFamily: 'DMSans-Bold', fontSize: 18, color: colors.accent },
askAiText: { fontFamily: 'DMSans-SemiBold', fontSize: 15, color: colors.textPrimary },
```

Need to import openAskAi from the store:
```tsx
const openAskAi = useReaderStore((s) => s.openAskAi);
```

- [ ] **Step 2: Commit**

```bash
git add reader/components/word-detail/IrabTab.tsx
git commit -m "style(reader): update IrabTab layout to match Paper design"
```

---

### Task 17: Update AskAiTab

**Files:**
- Modify: `reader/components/word-detail/AskAiTab.tsx`

- [ ] **Step 1: Update AskAiTab.tsx**

Paper design shows:
- "What would you like to know about [word]?" prompt with + icon
- Contextual suggestion chips: "Why is it [case] here?", "Explain the [construct] with [word]", "More words from root [root]"
- Input bar: "Ask anything about this word..." placeholder with gold send arrow button
- Send icon: arrow-right in a circle

Replace the send button unicode `↑` with Feather icon:
```tsx
import { Icon } from '../ui/Icon';

// In the send button:
<Icon name="arrow-right" size={18} color={colors.white} />
```

Update the suggestion label to match Paper:
```tsx
<View style={styles.suggestionsHeader}>
  <Icon name="plus" size={16} color={colors.accent} />
  <Text style={styles.suggestionsLabel}>
    What would you like to know about{' '}
    <Text style={styles.wordHighlight}>
      {selectedToken?.tashkeel ?? selectedToken?.text ?? 'this word'}
    </Text>
    ?
  </Text>
</View>
```

Update input placeholder:
```tsx
placeholder="Ask anything about this word..."
```

Update send button to use accent gold color:
```ts
sendButton: {
  width: 40,
  height: 40,
  borderRadius: borderRadius.full,
  backgroundColor: colors.accent,
  justifyContent: 'center',
  alignItems: 'center',
},
```

- [ ] **Step 2: Commit**

```bash
git add reader/components/word-detail/AskAiTab.tsx
git commit -m "style(reader): update AskAiTab with icons and gold send button"
```

---

### Task 18: Rewrite Profile Screen

**Files:**
- Modify: `reader/app/profile.tsx`

- [ ] **Step 1: Full rewrite of profile.tsx**

The Paper design shows:
1. Header: `< Library` back, "Profile" centered
2. Avatar circle (80px, dark brown, "YH"), full name below, email below that
3. 4-column stats row in a card: HOURS READ | BOOKS ACTIVE | COMPLETED | WORDS LEARNED
4. SUBSCRIPTION section: card with star icon, "Monthly Plan" + ACTIVE badge, price, "Manage" button, annual upsell row
5. ACCOUNT section: card with Name row (user icon + value + chevron) and Email row (mail icon + value + chevron)
6. SUPPORT section: card with Help Center (help-circle icon), Contact Us (message-square icon), Rate Suhuf (star icon) rows with chevrons
7. "Sign Out" button (full-width, bordered, red/accent text)
8. Version footer: "Suhuf v2.1.0 . Build 847"

Full replacement:

```tsx
import { useEffect, useMemo } from 'react';
import { ScrollView, View, Text, Pressable, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { useStatsStore } from '../stores/stats';
import { useLibraryStore } from '../stores/library';
import { Header } from '../components/ui/Header';
import { Icon, IconName } from '../components/ui/Icon';
import { colors, spacing, typography, borderRadius } from '../constants/theme';

function Avatar() {
  return (
    <View style={styles.avatarContainer}>
      <View style={styles.avatar}>
        <Text style={styles.avatarText}>YH</Text>
      </View>
      <Text style={styles.fullName}>Yousef Hassan</Text>
      <Text style={styles.email}>yousef@example.com</Text>
    </View>
  );
}

function StatsBar({ hoursRead, booksActive, completed, wordsLearned }: {
  hoursRead: string; booksActive: number; completed: number; wordsLearned: string;
}) {
  const stats = [
    { label: 'HOURS READ', value: hoursRead },
    { label: 'BOOKS ACTIVE', value: booksActive },
    { label: 'COMPLETED', value: completed },
    { label: 'WORDS LEARNED', value: wordsLearned },
  ];
  return (
    <View style={styles.statsCard}>
      {stats.map((s, i) => (
        <View key={s.label} style={[styles.statCol, i < stats.length - 1 && styles.statBorder]}>
          <Text style={styles.statValue}>{s.value}</Text>
          <Text style={styles.statLabel}>{s.label}</Text>
        </View>
      ))}
    </View>
  );
}

function SectionTitle({ title }: { title: string }) {
  return <Text style={styles.sectionTitle}>{title}</Text>;
}

function SettingsRow({ icon, label, value, onPress, destructive }: {
  icon: IconName; label: string; value?: string; onPress?: () => void; destructive?: boolean;
}) {
  return (
    <Pressable style={styles.settingsRow} onPress={onPress}>
      <Icon name={icon} size={18} color={destructive ? colors.error : colors.textSecondary} />
      <Text style={[styles.rowLabel, destructive && styles.destructiveLabel]}>{label}</Text>
      <View style={styles.rowRight}>
        {value ? <Text style={styles.rowValue}>{value}</Text> : null}
        <Icon name="chevron-right" size={16} color={colors.textTertiary} />
      </View>
    </Pressable>
  );
}

function RowDivider() {
  return <View style={styles.divider} />;
}

export default function ProfileScreen() {
  const router = useRouter();
  const { today, totalTimeToday, loadStats } = useStatsStore();
  const { downloadedBooks, loadDownloadedBooks } = useLibraryStore();

  useEffect(() => {
    loadStats();
    loadDownloadedBooks();
  }, []);

  const hoursReadDisplay = useMemo(() => {
    const h = Math.floor(today.time_seconds / 3600);
    return h > 0 ? `${h}` : '0';
  }, [today.time_seconds]);

  const booksActive = useMemo(() => {
    return downloadedBooks.filter((b) => {
      if (b.page_count <= 0) return false;
      const pct = b.last_read_page / b.page_count;
      return pct > 0 && pct < 1;
    }).length;
  }, [downloadedBooks]);

  const booksCompleted = useMemo(() => {
    return downloadedBooks.filter((b) => {
      if (b.page_count <= 0) return false;
      return b.last_read_page / b.page_count >= 1;
    }).length;
  }, [downloadedBooks]);

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <Header title="Profile" showBack />
      <Avatar />
      <View style={styles.section}>
        <StatsBar
          hoursRead={hoursReadDisplay}
          booksActive={booksActive}
          completed={booksCompleted}
          wordsLearned={today.words_learned > 999 ? `${(today.words_learned / 1000).toFixed(1)}k` : String(today.words_learned)}
        />
      </View>

      {/* SUBSCRIPTION */}
      <View style={styles.section}>
        <SectionTitle title="SUBSCRIPTION" />
        <View style={styles.card}>
          <View style={styles.subRow}>
            <Icon name="star" size={20} color={colors.accent} />
            <View style={styles.subInfo}>
              <View style={styles.subTitleRow}>
                <Text style={styles.subPlan}>Monthly Plan</Text>
                <View style={styles.activeBadge}>
                  <Text style={styles.activeBadgeText}>ACTIVE</Text>
                </View>
              </View>
              <Text style={styles.subPrice}>$7.99/month · Renews May 12, 2026</Text>
            </View>
            <Pressable><Text style={styles.manageText}>Manage</Text></Pressable>
          </View>
          <RowDivider />
          <View style={styles.upsellRow}>
            <Text style={styles.upsellText}>Save 37% with annual billing</Text>
            <Pressable><Text style={styles.switchText}>Switch to Annual</Text></Pressable>
          </View>
        </View>
      </View>

      {/* ACCOUNT */}
      <View style={styles.section}>
        <SectionTitle title="ACCOUNT" />
        <View style={styles.card}>
          <SettingsRow icon="user" label="Name" value="Yousef Hassan" />
          <RowDivider />
          <SettingsRow icon="mail" label="Email" value="yousef@example.com" />
        </View>
      </View>

      {/* SUPPORT */}
      <View style={styles.section}>
        <SectionTitle title="SUPPORT" />
        <View style={styles.card}>
          <SettingsRow icon="help-circle" label="Help Center" />
          <RowDivider />
          <SettingsRow icon="message-square" label="Contact Us" />
          <RowDivider />
          <SettingsRow icon="star" label="Rate Suhuf" />
        </View>
      </View>

      {/* Sign Out */}
      <View style={styles.section}>
        <Pressable style={styles.signOutButton}>
          <Text style={styles.signOutText}>Sign Out</Text>
        </Pressable>
      </View>

      {/* Version */}
      <Text style={styles.versionText}>Suhuf v2.1.0 · Build 847</Text>

      <View style={styles.bottomPad} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { gap: spacing.lg, paddingBottom: spacing.xxl },

  avatarContainer: { alignItems: 'center', paddingTop: spacing.lg, gap: spacing.xs },
  avatar: {
    width: 72, height: 72, borderRadius: 36,
    backgroundColor: colors.primary,
    justifyContent: 'center', alignItems: 'center',
    borderWidth: 2, borderColor: colors.cardBorder,
  },
  avatarText: { fontSize: 24, fontWeight: '700', color: colors.white, fontFamily: 'DMSans-Bold' },
  fullName: { fontFamily: 'DMSans-SemiBold', fontSize: 20, color: colors.textPrimary, marginTop: spacing.sm },
  email: { fontFamily: 'DMSans', fontSize: 14, color: colors.textSecondary },

  section: { paddingHorizontal: spacing.screenPadding, gap: spacing.sm },
  sectionTitle: { ...typography.label, fontFamily: 'DMSans-Medium', color: colors.textSecondary },

  card: {
    backgroundColor: colors.card, borderRadius: borderRadius.lg,
    borderWidth: 1, borderColor: colors.cardBorder, overflow: 'hidden',
  },
  divider: { height: 1, backgroundColor: colors.cardBorder, marginHorizontal: spacing.md },

  statsCard: {
    flexDirection: 'row', backgroundColor: colors.card, borderRadius: borderRadius.lg,
    borderWidth: 1, borderColor: colors.cardBorder, overflow: 'hidden',
  },
  statCol: { flex: 1, alignItems: 'center', paddingVertical: spacing.md, gap: spacing.xs },
  statBorder: { borderRightWidth: 1, borderRightColor: colors.cardBorder },
  statValue: { fontFamily: 'DMSans-Bold', fontSize: 22, color: colors.textPrimary },
  statLabel: { ...typography.statLabel, fontFamily: 'DMSans-Medium', color: colors.textSecondary },

  subRow: { flexDirection: 'row', alignItems: 'center', padding: spacing.md, gap: spacing.sm },
  subInfo: { flex: 1, gap: 2 },
  subTitleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  subPlan: { fontFamily: 'DMSans-SemiBold', fontSize: 15, color: colors.textPrimary },
  activeBadge: {
    backgroundColor: colors.success, borderRadius: borderRadius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 2,
  },
  activeBadgeText: { fontFamily: 'DMSans-Bold', fontSize: 10, color: colors.white, letterSpacing: 0.5 },
  subPrice: { fontFamily: 'DMSans', fontSize: 13, color: colors.textSecondary },
  manageText: { fontFamily: 'DMSans-SemiBold', fontSize: 14, color: colors.accent },

  upsellRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  upsellText: { fontFamily: 'DMSans', fontSize: 13, color: colors.textSecondary },
  switchText: { fontFamily: 'DMSans-SemiBold', fontSize: 14, color: colors.accent },

  settingsRow: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  rowLabel: { flex: 1, fontFamily: 'DMSans', fontSize: 15, color: colors.textPrimary },
  rowRight: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  rowValue: { fontFamily: 'DMSans', fontSize: 14, color: colors.textSecondary },
  destructiveLabel: { color: colors.error },

  signOutButton: {
    backgroundColor: colors.card, borderRadius: borderRadius.lg,
    borderWidth: 1, borderColor: colors.cardBorder,
    paddingVertical: spacing.md, alignItems: 'center',
  },
  signOutText: { fontFamily: 'DMSans-SemiBold', fontSize: 15, color: colors.error },
  versionText: {
    fontFamily: 'DMSans', fontSize: 12, color: colors.textTertiary,
    textAlign: 'center', paddingTop: spacing.sm,
  },

  bottomPad: { height: spacing.xl },
});
```

- [ ] **Step 2: Commit**

```bash
git add reader/app/profile.tsx
git commit -m "feat(reader): rewrite Profile screen to match Paper design"
```

---

### Task 19: Rewrite Settings Screen

**Files:**
- Modify: `reader/app/settings.tsx`

- [ ] **Step 1: Full rewrite of settings.tsx**

The Paper design shows grouped sections with icon + label + value + chevron rows. Toggle for notifications. Simple, clean layout matching iOS settings style.

```tsx
import { ScrollView, View, Text, Pressable, Switch, StyleSheet } from 'react-native';
import { useSettingsStore } from '../stores/settings';
import { Header } from '../components/ui/Header';
import { Icon, IconName } from '../components/ui/Icon';
import { colors, spacing, typography, borderRadius } from '../constants/theme';

function SectionTitle({ title }: { title: string }) {
  return <Text style={styles.sectionTitle}>{title}</Text>;
}

function RowDivider() {
  return <View style={styles.divider} />;
}

function SettingsRow({ icon, label, value, onPress, destructive }: {
  icon: IconName; label: string; value?: string; onPress?: () => void; destructive?: boolean;
}) {
  return (
    <Pressable style={styles.row} onPress={onPress}>
      <Icon name={icon} size={18} color={destructive ? colors.error : colors.textSecondary} />
      <Text style={[styles.rowLabel, destructive && styles.destructiveText]}>{label}</Text>
      <View style={styles.rowRight}>
        {value ? <Text style={styles.rowValue}>{value}</Text> : null}
        <Icon name="chevron-right" size={16} color={colors.textTertiary} />
      </View>
    </Pressable>
  );
}

function ToggleRow({ icon, label, value, onToggle }: {
  icon: IconName; label: string; value: boolean; onToggle: () => void;
}) {
  return (
    <View style={styles.row}>
      <Icon name={icon} size={18} color={colors.textSecondary} />
      <Text style={styles.rowLabel}>{label}</Text>
      <Switch
        value={value}
        onValueChange={onToggle}
        trackColor={{ false: colors.cardBorder, true: colors.accent }}
        thumbColor={colors.white}
      />
    </View>
  );
}

const FONT_SIZE_LABELS: Record<number, string> = {
  18: 'Small', 20: 'Small', 22: 'Medium', 24: 'Large', 26: 'Large', 28: 'X-Large', 30: 'X-Large', 32: 'X-Large',
};

export default function SettingsScreen() {
  const {
    fontSize, arabicFont, aiLanguage, grammarDetail, notificationsEnabled,
    setFontSize, setArabicFont, setAiLanguage, setGrammarDetail, toggleNotifications,
  } = useSettingsStore();

  const fontSizeLabel = FONT_SIZE_LABELS[fontSize] ?? `${fontSize}`;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <Header title="Settings" showBack backLabel="Profile" />

      {/* READING */}
      <View style={styles.section}>
        <SectionTitle title="READING" />
        <View style={styles.card}>
          <SettingsRow icon="type" label="Font Size" value={fontSizeLabel} />
          <RowDivider />
          <SettingsRow icon="smartphone" label="Arabic Font" value={arabicFont} />
        </View>
      </View>

      {/* AI ASSISTANT */}
      <View style={styles.section}>
        <SectionTitle title="AI ASSISTANT" />
        <View style={styles.card}>
          <SettingsRow icon="message-square" label="Explanation Language" value={aiLanguage} />
          <RowDivider />
          <SettingsRow icon="list" label="Grammar Detail Level" value={grammarDetail} />
        </View>
      </View>

      {/* NOTIFICATIONS */}
      <View style={styles.section}>
        <SectionTitle title="NOTIFICATIONS" />
        <View style={styles.card}>
          <ToggleRow icon="bell" label="Daily Reading Reminder" value={notificationsEnabled} onToggle={toggleNotifications} />
          <RowDivider />
          <SettingsRow icon="clock" label="Reminder Time" value="8:00 AM" />
        </View>
      </View>

      {/* DATA & PRIVACY */}
      <View style={styles.section}>
        <SectionTitle title="DATA & PRIVACY" />
        <View style={styles.card}>
          <SettingsRow icon="upload-cloud" label="Export Reading Data" />
          <RowDivider />
          <SettingsRow icon="trash-2" label="Delete Account" destructive />
        </View>
      </View>

      <View style={styles.bottomPad} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { gap: spacing.lg, paddingBottom: spacing.xxl },

  section: { paddingHorizontal: spacing.screenPadding, gap: spacing.sm },
  sectionTitle: { ...typography.label, fontFamily: 'DMSans-Medium', color: colors.textSecondary },

  card: {
    backgroundColor: colors.card, borderRadius: borderRadius.lg,
    borderWidth: 1, borderColor: colors.cardBorder, overflow: 'hidden',
  },
  divider: { height: 1, backgroundColor: colors.cardBorder, marginHorizontal: spacing.md },

  row: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  rowLabel: { flex: 1, fontFamily: 'DMSans', fontSize: 15, color: colors.textPrimary },
  rowRight: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  rowValue: { fontFamily: 'DMSans', fontSize: 14, color: colors.textSecondary },
  destructiveText: { color: colors.error },

  bottomPad: { height: spacing.xl },
});
```

- [ ] **Step 2: Commit**

```bash
git add reader/app/settings.tsx
git commit -m "feat(reader): rewrite Settings screen to match Paper design"
```

---

### Task 20: Visual Verification

- [ ] **Step 1: Run the app and verify each screen**

```bash
cd reader && npx expo start
```

Open on iOS simulator. Walk through each screen and compare to Paper designs:
1. Library Main: serif "Library" title, 2x2 stats, search icon, "YH" avatar
2. Continue Reading: author + category inline, no category pill
3. Filtered tabs: dot+text pills, "Full Library" button
4. Discover: search icon in bar, sort icon button
5. Reading Session: bookmark/menu icons, tashkeel eye icon, Start button
6. Word popup: Feather icons
7. Word Detail: centered word, underlined tabs, proper section layout
8. Profile: subscription, account, support sections, sign out
9. Settings: icon+label+value+chevron rows, toggle switch

- [ ] **Step 2: Fix any visual discrepancies found during verification**

Address spacing, color, or layout issues that only become apparent when running the app.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "style(reader): fix visual polish from Paper design verification"
```
