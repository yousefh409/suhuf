import { useEffect, useMemo } from 'react';
import { ScrollView, View, Text, Pressable, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { useLibraryStore } from '../stores/library';
import { useStatsStore } from '../stores/stats';
import { Header } from '../components/ui/Header';
import { Icon } from '../components/ui/Icon';
import { StatsRow } from '../components/library/StatsRow';
import { ContinueReading } from '../components/library/ContinueReading';
import { FilteredTabs } from '../components/library/FilteredTabs';
import { BookGrid } from '../components/library/BookGrid';
import { colors, spacing, typography } from '../constants/theme';

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

const headerIconStyles = StyleSheet.create({
  btn: { padding: 4 },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarText: { fontSize: 13, fontWeight: '700', color: '#FFFFFF', fontFamily: 'DMSans-Bold' },
});

export default function LibraryMain() {
  const { catalog, downloadedBooks, loadCatalog, loadDownloadedBooks } = useLibraryStore();
  const { today, streak, totalTimeToday, loadStats } = useStatsStore();

  useEffect(() => {
    loadCatalog();
    loadDownloadedBooks();
    loadStats();
  }, []);

  // Build progress map: book_id -> fraction read
  const progressMap = useMemo(() => {
    const map: Record<string, number> = {};
    for (const book of downloadedBooks) {
      map[book.id] = book.page_count > 0 ? book.last_read_page / book.page_count : 0;
    }
    return map;
  }, [downloadedBooks]);

  // In-progress: downloaded, 0 < progress < 1
  const inProgress = useMemo(
    () => downloadedBooks.filter((b) => {
      const pct = progressMap[b.id] ?? 0;
      return pct > 0 && pct < 1;
    }),
    [downloadedBooks, progressMap]
  );

  // Completed: progress === 1
  const completed = useMemo(
    () => downloadedBooks.filter((b) => (progressMap[b.id] ?? 0) >= 1),
    [downloadedBooks, progressMap]
  );

  // Recommended: first 10 from catalog not yet in downloaded
  const downloadedIds = useMemo(() => new Set(downloadedBooks.map((b) => b.id)), [downloadedBooks]);
  const recommended = useMemo(
    () => catalog.filter((b) => !downloadedIds.has(b.id)).slice(0, 10),
    [catalog, downloadedIds]
  );

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
    >
      <Header
        title="Library"
        rightContent={
          <>
            <SearchIcon />
            <ProfileAvatar />
          </>
        }
      />

      {/* Stats row */}
      <StatsRow
        pagesToday={today.pages_read}
        wordsLearned={today.words_learned}
        streak={streak}
        timeRead={totalTimeToday}
      />

      {/* Continue Reading section */}
      {inProgress.length > 0 && (
        <>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Continue Reading</Text>
            <Text style={styles.sectionSub}>Last opened</Text>
          </View>
          <ContinueReading books={inProgress} progress={progressMap} />
        </>
      )}

      {/* Filtered tabs (In Progress / Saved / Completed) */}
      <FilteredTabs
        inProgress={inProgress}
        saved={[]}
        completed={completed}
        progressMap={progressMap}
      />

      {/* Recommended section */}
      {recommended.length > 0 && (
        <>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Recommended for You</Text>
            <Text style={styles.sectionSub}>Based on your reading</Text>
          </View>
          <BookGrid books={recommended} progressMap={progressMap} maxRows={2} />
        </>
      )}

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
    gap: spacing.sectionGap,
    paddingBottom: spacing.xxl,
  },
  sectionHeader: {
    paddingHorizontal: spacing.screenPadding,
    gap: 2,
  },
  sectionTitle: {
    ...typography.sectionTitle,
    fontFamily: 'CormorantGaramond-SemiBold',
    color: colors.textPrimary,
  },
  sectionSub: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  bottomPad: { height: spacing.xl },
});
