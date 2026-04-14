import { View, Text, ScrollView, Pressable, StyleSheet } from 'react-native';
import { useReaderStore } from '../../stores/reader';
import { colors, spacing, borderRadius, typography } from '../../constants/theme';

export function IrabTab() {
  const irabResult = useReaderStore((s) => s.irabResult);
  const selectedToken = useReaderStore((s) => s.selectedToken);
  const analysisError = useReaderStore((s) => s.analysisError);
  const openAskAi = useReaderStore((s) => s.openAskAi);

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
      {/* TYPE + CASE side by side */}
      <View style={styles.twoCol}>
        <View style={styles.col}>
          <Text style={styles.sectionLabel}>TYPE</Text>
          <Text style={styles.arabicValue}>{irabResult.pos_ar ?? irabResult.pos}</Text>
          <Text style={styles.englishValue}>{irabResult.pos}</Text>
        </View>
        {irabResult.case && (
          <View style={styles.col}>
            <Text style={styles.sectionLabel}>CASE</Text>
            <Text style={styles.arabicValue}>{irabResult.case_ar ?? irabResult.case}</Text>
            <Text style={styles.englishValue}>{irabResult.case}</Text>
          </View>
        )}
      </View>

      {/* ROLE */}
      {irabResult.role && (
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>ROLE</Text>
          <Text style={styles.arabicValue}>{irabResult.role_ar ?? irabResult.role}</Text>
          <Text style={styles.englishValue}>{irabResult.role}</Text>
        </View>
      )}

      {/* MARKER */}
      {irabResult.marker && (
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>MARKER</Text>
          <Text style={styles.arabicValue}>{irabResult.marker_ar ?? irabResult.marker}</Text>
          <Text style={styles.englishValue}>{irabResult.marker}</Text>
        </View>
      )}

      {/* WHY THIS CASE? */}
      {irabResult.why && (
        <View style={styles.whyCard}>
          <Text style={styles.sectionLabel}>WHY THIS CASE?</Text>
          <Text style={styles.whyText}>{irabResult.why}</Text>
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
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: spacing.xxl,
  },
  section: {
    gap: spacing.xs,
  },
  sectionLabel: {
    fontFamily: 'DMSans-Medium',
    ...typography.label,
    color: colors.textTertiary,
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
    fontSize: 22,
    color: colors.textPrimary,
    writingDirection: 'rtl',
  },
  englishValue: {
    fontFamily: 'DMSans',
    fontSize: 13,
    color: colors.textSecondary,
  },
  whyCard: {
    backgroundColor: '#F5EDD0',
    borderRadius: borderRadius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  whyText: {
    fontFamily: 'DMSans',
    fontSize: 15,
    color: colors.textPrimary,
    lineHeight: 24,
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
