import { useState } from 'react';
import { View, Text, Pressable, ScrollView, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import type { Book, DownloadedBook } from '../../types';
import { colors, spacing, borderRadius, typography } from '../../constants/theme';
import { BookCard } from './BookCard';

type TabKey = 'inProgress' | 'saved' | 'completed';

interface FilteredTabsProps {
  inProgress: DownloadedBook[];
  saved: Book[];
  completed: DownloadedBook[];
  progressMap: Record<string, number>;
}

const TABS: { key: TabKey; label: string }[] = [
  { key: 'inProgress', label: 'In Progress' },
  { key: 'saved', label: 'Saved' },
  { key: 'completed', label: 'Completed' },
];

export function FilteredTabs({ inProgress, saved, completed, progressMap }: FilteredTabsProps) {
  const [activeTab, setActiveTab] = useState<TabKey>('inProgress');
  const router = useRouter();

  const counts: Record<TabKey, number> = {
    inProgress: inProgress.length,
    saved: saved.length,
    completed: completed.length,
  };

  const books: Array<Book | DownloadedBook> =
    activeTab === 'inProgress' ? inProgress :
    activeTab === 'saved' ? saved :
    completed;

  return (
    <View>
      {/* Tab row */}
      <View style={styles.tabRow}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.pills}>
          {TABS.map((tab) => {
            const active = activeTab === tab.key;
            const dotColor = tab.key === 'inProgress' ? colors.accent : colors.textTertiary;
            return (
              <Pressable
                key={tab.key}
                style={[styles.pill, active && styles.pillActive]}
                onPress={() => setActiveTab(tab.key)}
              >
                <View style={[styles.dot, { backgroundColor: dotColor }]} />
                <Text style={[styles.pillText, active && styles.pillTextActive]}>
                  {tab.label}
                </Text>
                <Text style={styles.pillCount}>{counts[tab.key]}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
        <Pressable onPress={() => router.push('/discover')} style={styles.fullLibraryBtn}>
          <Text style={styles.fullLibraryText}>Full Library →</Text>
        </Pressable>
      </View>

      {/* Book scroll */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.bookScroll}
      >
        {books.map((book) => (
          <BookCard
            key={book.id}
            book={book}
            variant="medium"
            progress={'last_read_page' in book ? progressMap[book.id] : undefined}
          />
        ))}
        {books.length === 0 && (
          <Text style={styles.empty}>Nothing here yet.</Text>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  tabRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.screenPadding,
    marginBottom: spacing.md,
  },
  pills: {
    flexDirection: 'row',
    gap: spacing.sm,
    flexGrow: 0,
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
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  pillText: {
    ...typography.caption,
    color: colors.textSecondary,
    fontWeight: '500',
  },
  pillTextActive: {
    color: '#FFFFFF',
    fontWeight: '700',
  },
  pillCount: {
    fontSize: 11,
    color: colors.textTertiary,
  },
  fullLibraryBtn: {
    marginLeft: spacing.md,
    paddingVertical: spacing.sm,
  },
  fullLibraryText: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.accent,
  },
  bookScroll: {
    paddingHorizontal: spacing.screenPadding,
    gap: spacing.md,
  },
  empty: {
    ...typography.caption,
    color: colors.textSecondary,
    paddingVertical: spacing.md,
  },
});
