import { View, Text, ScrollView, StyleSheet } from 'react-native';
import { useReaderStore } from '../../stores/reader';
import { colors, spacing, borderRadius, typography } from '../../constants/theme';

export function IrabTab() {
  const irabResult = useReaderStore((s) => s.irabResult);
  const selectedToken = useReaderStore((s) => s.selectedToken);
  const analysisError = useReaderStore((s) => s.analysisError);

  if (analysisError) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorText}>{analysisError}</Text>
      </View>
    );
  }

  if (!irabResult) {
    return (
      <View style={styles.centered}>
        <Text style={styles.emptyText}>No grammar analysis available.</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
    >
      {/* Arabic word large display */}
      <View style={styles.wordHeader}>
        <Text style={styles.arabicWord}>{selectedToken?.tashkeel ?? selectedToken?.text}</Text>
        <Text style={styles.posTag}>{irabResult.pos}</Text>
      </View>

      {/* Grammatical tags row */}
      <View style={styles.tagsRow}>
        {irabResult.role ? (
          <View style={styles.tag}>
            <Text style={styles.tagLabel}>Role</Text>
            <Text style={styles.tagValue}>{irabResult.role}</Text>
            {irabResult.role_ar ? (
              <Text style={styles.tagValueAr}>{irabResult.role_ar}</Text>
            ) : null}
          </View>
        ) : null}

        {irabResult.case ? (
          <View style={styles.tag}>
            <Text style={styles.tagLabel}>Case</Text>
            <Text style={styles.tagValue}>{irabResult.case}</Text>
            {irabResult.case_ar ? (
              <Text style={styles.tagValueAr}>{irabResult.case_ar}</Text>
            ) : null}
          </View>
        ) : null}

        {irabResult.marker ? (
          <View style={styles.tag}>
            <Text style={styles.tagLabel}>Marker</Text>
            <Text style={styles.tagValue}>{irabResult.marker}</Text>
            {irabResult.marker_ar ? (
              <Text style={styles.tagValueAr}>{irabResult.marker_ar}</Text>
            ) : null}
          </View>
        ) : null}
      </View>

      {/* Meaning */}
      {irabResult.meaning ? (
        <View style={styles.meaningCard}>
          <Text style={styles.cardLabel}>MEANING</Text>
          <Text style={styles.meaningText}>{irabResult.meaning}</Text>
        </View>
      ) : null}

      {/* Why explanation card */}
      {irabResult.why ? (
        <View style={styles.whyCard}>
          <Text style={styles.cardLabel}>WHY IS IT {irabResult.case?.toUpperCase() ?? 'THIS CASE'} HERE?</Text>
          <Text style={styles.whyText}>{irabResult.why}</Text>
        </View>
      ) : null}
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
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: spacing.xxl,
  },
  wordHeader: {
    alignItems: 'flex-end',
    gap: spacing.xs,
    paddingVertical: spacing.sm,
  },
  arabicWord: {
    fontFamily: 'NotoNaskhArabic-Bold',
    fontSize: 36,
    color: colors.textPrimary,
    textAlign: 'right',
  },
  posTag: {
    fontFamily: 'DMSans-Medium',
    fontSize: 13,
    color: colors.accent,
    backgroundColor: '#F5EDD0',
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: borderRadius.full,
  },
  tagsRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    flexWrap: 'wrap',
  },
  tag: {
    flex: 1,
    minWidth: 90,
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    padding: spacing.sm,
    gap: 2,
    alignItems: 'center',
  },
  tagLabel: {
    fontFamily: 'DMSans-SemiBold',
    ...typography.label,
    color: colors.textTertiary,
  },
  tagValue: {
    fontFamily: 'DMSans-Medium',
    fontSize: 14,
    color: colors.textPrimary,
  },
  tagValueAr: {
    fontFamily: 'NotoNaskhArabic',
    fontSize: 16,
    color: colors.textSecondary,
    textAlign: 'center',
  },
  meaningCard: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    padding: spacing.md,
    gap: spacing.sm,
  },
  whyCard: {
    backgroundColor: '#F5EDD0',
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: '#E8D8A0',
    padding: spacing.md,
    gap: spacing.sm,
  },
  cardLabel: {
    fontFamily: 'DMSans-SemiBold',
    ...typography.label,
    color: colors.textTertiary,
  },
  meaningText: {
    fontFamily: 'DMSans',
    ...typography.body,
    color: colors.textPrimary,
  },
  whyText: {
    fontFamily: 'DMSans',
    ...typography.body,
    color: colors.textPrimary,
    lineHeight: 24,
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
