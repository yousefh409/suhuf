import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing, borderRadius, typography } from '../../constants/theme';

interface StatCardProps {
  label: string;
  value: string | number;
  unit?: string;
}

function StatCard({ label, value, unit }: StatCardProps) {
  return (
    <View style={styles.card}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.valueRow}>
        <Text style={styles.value}>{value}</Text>
        {unit ? <Text style={styles.unit}> {unit}</Text> : null}
      </View>
    </View>
  );
}

interface StatsRowProps {
  pagesToday: number;
  wordsLearned: number;
  streak: number;
  timeRead: string;
}

export function StatsRow({ pagesToday, wordsLearned, streak, timeRead }: StatsRowProps) {
  return (
    <View style={styles.grid}>
      <View style={styles.row}>
        <StatCard label="TODAY" value={pagesToday} unit="pages" />
        <StatCard label="WORDS LEARNED" value={wordsLearned} unit="this week" />
      </View>
      <View style={styles.row}>
        <StatCard label="STREAK" value={streak} unit="days" />
        <StatCard label="TIME READ" value={timeRead} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    paddingHorizontal: spacing.screenPadding,
    gap: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  card: {
    flex: 1,
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    alignItems: 'center',
  },
  label: {
    ...typography.statLabel,
    fontFamily: 'DMSans-Medium',
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  valueRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  value: {
    ...typography.stat,
    fontFamily: 'DMSans-Bold',
    color: colors.textPrimary,
  },
  unit: {
    fontSize: 12,
    fontFamily: 'DMSans',
    color: colors.textSecondary,
  },
});
