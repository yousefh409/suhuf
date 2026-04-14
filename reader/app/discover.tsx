import { useEffect, useMemo, useState } from 'react';
import { ScrollView, View, Text, TextInput, Pressable, StyleSheet } from 'react-native';
import { useLibraryStore } from '../stores/library';
import { Header } from '../components/ui/Header';
import { Icon } from '../components/ui/Icon';
import { CategoryPills } from '../components/library/CategoryPills';
import { BookGrid } from '../components/library/BookGrid';
import type { BookCategory } from '../types';
import { colors, spacing, borderRadius, typography } from '../constants/theme';

export default function Discover() {
  const { catalog, selectedCategory, isLoading, loadCatalog, filterByCategory, search } =
    useLibraryStore();
  const [query, setQuery] = useState('');

  useEffect(() => {
    loadCatalog();
  }, []);

  const handleCategorySelect = (cat: BookCategory | null) => {
    filterByCategory(cat);
    setQuery('');
  };

  const handleSearch = (text: string) => {
    setQuery(text);
    search(text);
  };

  // Category counts from current full catalog (approximate)
  const categoryCounts = useMemo(() => {
    const counts: Partial<Record<BookCategory, number>> = {};
    for (const book of catalog) {
      counts[book.category] = (counts[book.category] ?? 0) + 1;
    }
    return counts;
  }, [catalog]);

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
    >
      <Header title="Discover" showBack />

      {/* Search bar */}
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

      {/* Category pills */}
      <CategoryPills
        selected={selectedCategory}
        counts={categoryCounts}
        onSelect={handleCategorySelect}
      />

      {/* Sort + count row */}
      <View style={styles.sortRow}>
        <Text style={styles.resultCount}>
          {isLoading ? 'Loading...' : `${selectedCategory ? `${selectedCategory} \u00b7 ` : ''}${catalog.length.toLocaleString()} texts`}
        </Text>
        <Pressable style={styles.sortButton}>
          <Icon name="sliders" size={16} color={colors.textPrimary} />
          <Text style={styles.sortText}>Sort</Text>
        </Pressable>
      </View>

      {/* Book grid */}
      <BookGrid books={catalog} />

      <View style={styles.bottomPad} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    gap: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  searchContainer: {
    paddingHorizontal: spacing.screenPadding,
  },
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
  sortRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.screenPadding,
  },
  resultCount: {
    ...typography.caption,
    color: colors.textSecondary,
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
  sortText: {
    fontSize: 13,
    fontFamily: 'DMSans-SemiBold',
    color: colors.textPrimary,
  },
  bottomPad: { height: spacing.xl },
});
