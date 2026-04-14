import { useEffect, useRef, useCallback } from 'react';
import {
  View,
  FlatList,
  Text,
  Pressable,
  ActivityIndicator,
  StyleSheet,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams } from 'expo-router';
import { useReaderStore } from '../../stores/reader';
import { PageView } from '../../components/reader/PageView';
import { TashkeelToggle } from '../../components/reader/TashkeelToggle';
import { WordPopup } from '../../components/reader/WordPopup';
import { WordDetailSheet } from '../../components/word-detail/WordDetailSheet';
import { Header } from '../../components/ui/Header';
import { Icon } from '../../components/ui/Icon';
import { colors, spacing, borderRadius } from '../../constants/theme';

export default function ReadingSession() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { width } = useWindowDimensions();

  const pages = useReaderStore((s) => s.pages);
  const currentPage = useReaderStore((s) => s.currentPage);
  const isLoadingBook = useReaderStore((s) => s.isLoadingBook);
  const downloadProgress = useReaderStore((s) => s.downloadProgress);
  const loadError = useReaderStore((s) => s.loadError);
  const loadBook = useReaderStore((s) => s.loadBook);
  const goToPage = useReaderStore((s) => s.goToPage);
  const clearSelection = useReaderStore((s) => s.clearSelection);
  const showWordPopup = useReaderStore((s) => s.showWordPopup);

  const flatListRef = useRef<FlatList>(null);

  useEffect(() => {
    if (id) loadBook(id);
  }, [id]);

  const handleMomentumScrollEnd = useCallback(
    (e: any) => {
      const pageIndex = Math.round(e.nativeEvent.contentOffset.x / width);
      goToPage(pageIndex + 1);
    },
    [width, goToPage]
  );

  const getItemLayout = useCallback(
    (_: any, index: number) => ({
      length: width,
      offset: width * index,
      index,
    }),
    [width]
  );

  // Dismiss popup when tapping outside a word
  const handleBackgroundPress = () => {
    if (showWordPopup) clearSelection();
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        {/* Header */}
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

        {/* Page content */}
        <Pressable style={styles.pageArea} onPress={handleBackgroundPress}>
          {pages.length > 0 ? (
            <FlatList
              ref={flatListRef}
              data={pages}
              horizontal
              pagingEnabled
              showsHorizontalScrollIndicator={false}
              keyExtractor={(p) => p.id}
              renderItem={({ item }) => (
                <PageView page={item} width={width} />
              )}
              onMomentumScrollEnd={handleMomentumScrollEnd}
              initialScrollIndex={currentPage - 1}
              getItemLayout={getItemLayout}
              decelerationRate="fast"
              bounces={false}
            />
          ) : (
            <View style={styles.emptyState}>
              {loadError ? (
                <>
                  <Icon name="alert-circle" size={32} color={colors.error} />
                  <Text style={styles.errorText}>{loadError}</Text>
                  <Pressable style={styles.retryButton} onPress={() => id && loadBook(id)}>
                    <Text style={styles.retryText}>Try Again</Text>
                  </Pressable>
                </>
              ) : downloadProgress && downloadProgress.total > 0 ? (
                <>
                  <Text style={styles.loadingTitle}>Downloading pages...</Text>
                  <View style={styles.progressBarContainer}>
                    <View
                      style={[
                        styles.progressBarFill,
                        { width: `${Math.round((downloadProgress.downloaded / downloadProgress.total) * 100)}%` },
                      ]}
                    />
                  </View>
                  <Text style={styles.progressText}>
                    {downloadProgress.downloaded} / {downloadProgress.total} pages
                  </Text>
                </>
              ) : (
                <>
                  <ActivityIndicator size="large" color={colors.accent} />
                  <Text style={styles.emptyText}>Loading book...</Text>
                </>
              )}
            </View>
          )}
        </Pressable>

        {/* Footer */}
        <View style={styles.footer}>
          <TashkeelToggle />
          <Text style={styles.pageNumber}>
            {currentPage} / {pages.length || '—'}
          </Text>
          <Pressable style={styles.startButton}>
            <Icon name="play" size={14} color={colors.white} />
            <Text style={styles.startText}>Start</Text>
          </Pressable>
        </View>

        {/* Word popup overlay */}
        <WordPopup />

        {/* Word detail bottom sheet */}
        <WordDetailSheet />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  pageArea: {
    flex: 1,
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.xl,
  },
  emptyText: {
    fontFamily: 'DMSans',
    fontSize: 16,
    color: colors.textTertiary,
  },
  loadingTitle: {
    fontFamily: 'DMSans-SemiBold',
    fontSize: 16,
    color: colors.textPrimary,
  },
  progressBarContainer: {
    width: '100%',
    height: 6,
    backgroundColor: colors.cardBorder,
    borderRadius: 3,
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    backgroundColor: colors.accent,
    borderRadius: 3,
  },
  progressText: {
    fontFamily: 'DMSans',
    fontSize: 14,
    color: colors.textSecondary,
  },
  errorText: {
    fontFamily: 'DMSans',
    fontSize: 15,
    color: colors.error,
    textAlign: 'center',
  },
  retryButton: {
    backgroundColor: colors.primary,
    borderRadius: borderRadius.full,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  retryText: {
    fontFamily: 'DMSans-SemiBold',
    fontSize: 14,
    color: colors.white,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.screenPadding,
    paddingVertical: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.cardBorder,
    backgroundColor: colors.background,
  },
  pageNumber: {
    fontFamily: 'DMSans',
    fontSize: 14,
    color: colors.textSecondary,
  },
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
});
