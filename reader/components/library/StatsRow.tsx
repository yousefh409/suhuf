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
        {unit ? <Text style={styles.unit}>{unit}</Text> : null}
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
    <View style={styles.row}>
      <StatCard label="TODAY" value={pagesToday} unit="pg" />
      <StatCard label="WORDS LEARNED" value={wordsLearned} />
      <StatCard label="STREAK" value={streak} unit="d" />
      <StatCard label="TIME READ" value={timeRead} />
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.screenPadding,
  },
  card: {
    flex: 1,
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.md,
    alignItems: 'flex-start',
  },
  label: {
    ...typography.statLabel,
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  valueRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 2,
  },
  value: {
    ...typography.stat,
    color: colors.textPrimary,
  },
  unit: {
    fontSize: 13,
    fontWeight: '500',
    color: colors.textSecondary,
    marginBottom: 6,
  },
});
