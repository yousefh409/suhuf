import { useEffect, useRef, useCallback } from 'react';
import {
  View,
  FlatList,
  Text,
  Pressable,
  StyleSheet,
  useWindowDimensions,
  SafeAreaView,
} from 'react-native';
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
              <Text style={styles.emptyText}>Loading book...</Text>
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
  },
  emptyText: {
    fontFamily: 'DMSans',
    fontSize: 16,
    color: colors.textTertiary,
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
