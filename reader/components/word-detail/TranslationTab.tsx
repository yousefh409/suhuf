import { View, Text, ScrollView, Pressable, StyleSheet } from 'react-native';
import { useReaderStore } from '../../stores/reader';
import { colors, spacing, borderRadius, typography } from '../../constants/theme';

export function TranslationTab() {
  const translationResult = useReaderStore((s) => s.translationResult);
  const selectedToken = useReaderStore((s) => s.selectedToken);
  const analysisError = useReaderStore((s) => s.analysisError);
  const openAskAi = useReaderStore((s) => s.openAskAi);

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
      {/* MEANING */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>MEANING</Text>
        <Text style={styles.meaningText}>{translationResult.translation}</Text>
      </View>

      {/* ROOT + PATTERN side by side */}
      {translationResult.related_words.length > 0 && (
        <View style={styles.twoCol}>
          <View style={styles.col}>
            <Text style={styles.sectionLabel}>ROOT</Text>
            <Text style={styles.arabicValue}>{translationResult.related_words[0].root}</Text>
          </View>
          <View style={styles.col}>
            <Text style={styles.sectionLabel}>PATTERN</Text>
            <Text style={styles.arabicValue}>{'\u0641\u0639\u064A\u0644'}</Text>
          </View>
        </View>
      )}

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
  );
}

const styles = StyleSheet.create({
  scroll: {
    flex: 1,
  },
  content: {
    gap: spacing.lg,
    paddingBottom: spacing.xl,
  },
  section: {
    gap: spacing.xs,
  },
  sectionLabel: {
    fontFamily: 'DMSans-Medium',
    ...typography.label,
    color: colors.textTertiary,
  },
  meaningText: {
    fontFamily: 'DMSans',
    fontSize: 15,
    color: colors.textPrimary,
    lineHeight: 24,
  },
  twoCol: {
    flexDirection: 'row',
    gap: spacing.lg,
  },
  col: {
    flex: 1,
    gap: spacing.xs,
  },
  arabicValue: {
    fontFamily: 'NotoNaskhArabic',
    fontSize: 20,
    color: colors.textPrimary,
    writingDirection: 'rtl',
  },
  pillsRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    flexWrap: 'wrap',
  },
  relatedPill: {
    flexDirection: 'row',
    gap: spacing.xs,
    alignItems: 'center',
    backgroundColor: colors.background,
    borderRadius: borderRadius.full,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  relatedPillArabic: {
    fontFamily: 'NotoNaskhArabic',
    fontSize: 16,
    color: colors.textPrimary,
  },
  relatedPillMeaning: {
    fontFamily: 'DMSans',
    fontSize: 13,
    color: colors.textSecondary,
  },
  askAiButton: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: '#F5EDD0',
    borderRadius: borderRadius.md,
    paddingVertical: spacing.md,
    marginTop: spacing.md,
  },
  askAiIcon: {
    fontFamily: 'DMSans-Bold',
    fontSize: 18,
    color: colors.accent,
  },
  askAiText: {
    fontFamily: 'DMSans-SemiBold',
    fontSize: 15,
    color: colors.textPrimary,
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
