import { useCallback, useMemo, useRef, useEffect } from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import BottomSheet, { BottomSheetView } from '@gorhom/bottom-sheet';
import { useReaderStore } from '../../stores/reader';
import { TranslationTab } from './TranslationTab';
import { IrabTab } from './IrabTab';
import { AskAiTab } from './AskAiTab';
import { LoadingState } from './LoadingState';
import { Icon } from '../ui/Icon';
import { colors, spacing, borderRadius, typography } from '../../constants/theme';

type Tab = 'translation' | 'irab' | 'ask-ai';

const TAB_LABELS: Record<Tab, string> = {
  translation: 'Translation',
  irab: 'I3rab',
  'ask-ai': 'Ask AI',
};

const TABS: Tab[] = ['translation', 'irab'];

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
        {/* Word header: centered arabic word + transliteration */}
        <View style={styles.wordHeader}>
          <Text style={styles.wordArabic}>{selectedToken.tashkeel}</Text>
          {irabResult?.meaning ? (
            <Text style={styles.wordTransliteration}>{irabResult.meaning}</Text>
          ) : null}
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
  tabContent: {
    flex: 1,
  },
});
