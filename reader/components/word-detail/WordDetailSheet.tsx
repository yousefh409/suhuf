import { useCallback, useMemo, useRef, useEffect } from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import BottomSheet, { BottomSheetView } from '@gorhom/bottom-sheet';
import { useReaderStore } from '../../stores/reader';
import { TranslationTab } from './TranslationTab';
import { IrabTab } from './IrabTab';
import { AskAiTab } from './AskAiTab';
import { LoadingState } from './LoadingState';
import { colors, spacing, borderRadius, typography } from '../../constants/theme';

type Tab = 'translation' | 'irab' | 'ask-ai';

const TAB_LABELS: Record<Tab, string> = {
  translation: 'Translate',
  irab: 'Grammar',
  'ask-ai': 'Ask AI',
};

const TABS: Tab[] = ['translation', 'irab', 'ask-ai'];

export function WordDetailSheet() {
  const bottomSheetRef = useRef<BottomSheet>(null);

  const showWordDetail = useReaderStore((s) => s.showWordDetail);
  const activeTab = useReaderStore((s) => s.activeTab);
  const selectedToken = useReaderStore((s) => s.selectedToken);
  const isLoadingAnalysis = useReaderStore((s) => s.isLoadingAnalysis);
  const irabResult = useReaderStore((s) => s.irabResult);
  const closeWordDetail = useReaderStore((s) => s.closeWordDetail);
  const openAskAi = useReaderStore((s) => s.openAskAi);

  const snapPoints = useMemo(() => ['50%', '88%'], []);

  // Open or close the sheet based on store state
  useEffect(() => {
    if (showWordDetail) {
      bottomSheetRef.current?.expand();
    } else {
      bottomSheetRef.current?.close();
    }
  }, [showWordDetail]);

  const handleSheetChanges = useCallback(
    (index: number) => {
      if (index === -1 && showWordDetail) {
        closeWordDetail();
      }
    },
    [showWordDetail, closeWordDetail]
  );

  const setActiveTab = (tab: Tab) => {
    useReaderStore.setState({ activeTab: tab });
  };

  if (!showWordDetail || !selectedToken) return null;

  return (
    <BottomSheet
      ref={bottomSheetRef}
      index={0}
      snapPoints={snapPoints}
      onChange={handleSheetChanges}
      enablePanDownToClose
      backgroundStyle={styles.background}
      handleIndicatorStyle={styles.handleIndicator}
    >
      <BottomSheetView style={styles.content}>
        {/* Header row: back arrow + arabic word + meaning + Ask AI button */}
        <View style={styles.wordHeader}>
          <Pressable
            onPress={closeWordDetail}
            style={styles.backButton}
            accessibilityRole="button"
            accessibilityLabel="Close"
          >
            <Text style={styles.backArrow}>{'‹'}</Text>
          </Pressable>

          <View style={styles.wordInfo}>
            <Text style={styles.wordArabic}>{selectedToken.tashkeel}</Text>
            {irabResult?.meaning ? (
              <Text style={styles.wordMeaning}>{irabResult.meaning}</Text>
            ) : null}
          </View>

          <Pressable
            style={styles.askAiButton}
            onPress={openAskAi}
            accessibilityRole="button"
            accessibilityLabel="Open Ask AI"
          >
            <Text style={styles.askAiText}>+ Ask AI</Text>
          </Pressable>
        </View>

        {/* Tab bar */}
        <View style={styles.tabBar}>
          {TABS.map((tab) => (
            <Pressable
              key={tab}
              style={[styles.tab, activeTab === tab && styles.tabActive]}
              onPress={() => setActiveTab(tab)}
              accessibilityRole="tab"
              accessibilityState={{ selected: activeTab === tab }}
            >
              <Text style={[styles.tabText, activeTab === tab && styles.tabTextActive]}>
                {TAB_LABELS[tab]}
              </Text>
            </Pressable>
          ))}
        </View>

        {/* Tab content */}
        <View style={styles.tabContent}>
          {isLoadingAnalysis ? (
            <LoadingState />
          ) : (
            <>
              {activeTab === 'translation' && <TranslationTab />}
              {activeTab === 'irab' && <IrabTab />}
              {activeTab === 'ask-ai' && <AskAiTab />}
            </>
          )}
        </View>
      </BottomSheetView>
    </BottomSheet>
  );
}

const styles = StyleSheet.create({
  background: {
    backgroundColor: colors.white,
    borderTopLeftRadius: borderRadius.xl,
    borderTopRightRadius: borderRadius.xl,
  },
  handleIndicator: {
    backgroundColor: colors.cardBorder,
    width: 40,
    height: 4,
  },
  content: {
    flex: 1,
    paddingHorizontal: spacing.screenPadding,
  },
  wordHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    gap: spacing.sm,
  },
  backButton: {
    padding: spacing.xs,
  },
  backArrow: {
    fontSize: 28,
    color: colors.textSecondary,
    lineHeight: 32,
  },
  wordInfo: {
    flex: 1,
    gap: 2,
  },
  wordArabic: {
    fontFamily: 'NotoNaskhArabic-Bold',
    fontSize: 28,
    color: colors.textPrimary,
    textAlign: 'right',
  },
  wordMeaning: {
    fontFamily: 'DMSans',
    fontSize: 13,
    color: colors.textSecondary,
    textAlign: 'right',
  },
  askAiButton: {
    backgroundColor: colors.background,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: colors.cardBorder,
  },
  askAiText: {
    fontFamily: 'DMSans-Medium',
    fontSize: 13,
    color: colors.textPrimary,
  },
  tabBar: {
    flexDirection: 'row',
    gap: spacing.xs,
    marginBottom: spacing.md,
  },
  tab: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.full,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.cardBorder,
  },
  tabActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  tabText: {
    fontFamily: 'DMSans-Medium',
    fontSize: 13,
    color: colors.textSecondary,
  },
  tabTextActive: {
    color: colors.white,
  },
  tabContent: {
    flex: 1,
  },
});
