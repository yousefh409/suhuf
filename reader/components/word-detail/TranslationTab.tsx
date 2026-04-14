import { View, Text, ScrollView, StyleSheet } from 'react-native';
import { useReaderStore } from '../../stores/reader';
import { colors, spacing, borderRadius, typography } from '../../constants/theme';

export function TranslationTab() {
  const translationResult = useReaderStore((s) => s.translationResult);
  const selectedToken = useReaderStore((s) => s.selectedToken);
  const analysisError = useReaderStore((s) => s.analysisError);

  if (analysisError) {
    return (
      <View style={styles.errorContainer}>
        <Text style={styles.errorText}>{analysisError}</Text>
      </View>
    );
  }

  if (!translationResult) {
    return (
      <View style={styles.errorContainer}>
        <Text style={styles.emptyText}>No translation available.</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
    >
      {/* Word + root display */}
      <View style={styles.wordHeader}>
        <Text style={styles.arabicWord}>{selectedToken?.tashkeel ?? selectedToken?.text}</Text>
      </View>

      {/* Translation card */}
      <View style={styles.card}>
        <Text style={styles.cardLabel}>TRANSLATION</Text>
        <Text style={styles.translationText}>{translationResult.translation}</Text>
      </View>

      {/* Related words */}
      {translationResult.related_words.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>RELATED WORDS</Text>
          {translationResult.related_words.map((rw, i) => (
            <View key={i} style={styles.relatedWordRow}>
              <View style={styles.relatedWordLeft}>
                <Text style={styles.relatedWordArabic}>{rw.word}</Text>
                <Text style={styles.relatedWordRoot}>root: {rw.root}</Text>
              </View>
              <Text style={styles.relatedWordMeaning}>{rw.meaning}</Text>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flex: 1,
  },
  content: {
    gap: spacing.md,
    paddingBottom: spacing.xl,
  },
  wordHeader: {
    alignItems: 'flex-end',
    paddingVertical: spacing.sm,
  },
  arabicWord: {
    fontFamily: 'NotoNaskhArabic-Bold',
    fontSize: 36,
    color: colors.textPrimary,
    textAlign: 'right',
  },
  card: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    padding: spacing.md,
    gap: spacing.sm,
  },
  cardLabel: {
    fontFamily: 'DMSans-SemiBold',
    ...typography.label,
    color: colors.textTertiary,
  },
  translationText: {
    fontFamily: 'DMSans',
    ...typography.body,
    color: colors.textPrimary,
    lineHeight: 26,
  },
  section: {
    gap: spacing.sm,
  },
  sectionLabel: {
    fontFamily: 'DMSans-SemiBold',
    ...typography.label,
    color: colors.textTertiary,
    marginTop: spacing.xs,
  },
  relatedWordRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.cardBorder,
  },
  relatedWordLeft: {
    gap: 2,
  },
  relatedWordArabic: {
    fontFamily: 'NotoNaskhArabic-Bold',
    fontSize: 20,
    color: colors.textPrimary,
    textAlign: 'right',
  },
  relatedWordRoot: {
    fontFamily: 'DMSans',
    fontSize: 12,
    color: colors.textTertiary,
  },
  relatedWordMeaning: {
    fontFamily: 'DMSans',
    fontSize: 14,
    color: colors.textSecondary,
    flex: 1,
    textAlign: 'right',
    paddingLeft: spacing.sm,
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: spacing.xxl,
  },
  errorText: {
    fontFamily: 'DMSans',
    fontSize: 14,
    color: colors.error,
    textAlign: 'center',
  },
  emptyText: {
    fontFamily: 'DMSans',
    fontSize: 14,
    color: colors.textTertiary,
    textAlign: 'center',
  },
});
