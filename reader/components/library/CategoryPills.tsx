import { ScrollView, View, Text, Pressable, StyleSheet } from 'react-native';
import type { BookCategory } from '../../types';
import { colors, spacing, borderRadius, typography } from '../../constants/theme';

const ALL_CATEGORIES: BookCategory[] = [
  'Nahw', 'Sarf', 'Hadith', 'Fiqh', 'Tafseer',
  'Aqeedah', 'Balagha', 'Lugha', 'Sirah',
];

interface CategoryPillsProps {
  selected: BookCategory | null;
  counts: Partial<Record<BookCategory, number>>;
  onSelect: (category: BookCategory | null) => void;
}

export function CategoryPills({ selected, counts, onSelect }: CategoryPillsProps) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.container}
    >
      {/* "All" pill */}
      <Pressable
        style={[styles.pill, selected === null && styles.pillActive]}
        onPress={() => onSelect(null)}
      >
        <Text style={[styles.pillText, selected === null && styles.pillTextActive]}>All</Text>
      </Pressable>

      {ALL_CATEGORIES.map((cat) => {
        const active = selected === cat;
        const count = counts[cat];
        return (
          <Pressable
            key={cat}
            style={[styles.pill, active && styles.pillActive]}
            onPress={() => onSelect(cat)}
          >
            <Text style={[styles.pillText, active && styles.pillTextActive]}>{cat}</Text>
            {count !== undefined && (
              <View style={[styles.badge, active && styles.badgeActive]}>
                <Text style={[styles.badgeText, active && styles.badgeTextActive]}>{count}</Text>
              </View>
            )}
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.screenPadding,
  },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: '#EDE8E2',
    borderRadius: borderRadius.full,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  pillActive: {
    backgroundColor: colors.primary,
  },
  pillText: {
    ...typography.caption,
    fontWeight: '500',
    color: colors.textSecondary,
  },
  pillTextActive: {
    color: '#FFFFFF',
    fontWeight: '700',
  },
  badge: {
    backgroundColor: colors.cardBorder,
    borderRadius: borderRadius.full,
    paddingHorizontal: 6,
    paddingVertical: 1,
  },
  badgeActive: {
    backgroundColor: 'rgba(255,255,255,0.25)',
  },
  badgeText: {
    fontSize: 11,
    color: colors.textSecondary,
  },
  badgeTextActive: {
    color: '#FFFFFF',
  },
});
