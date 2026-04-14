import { useEffect, useMemo } from 'react';
import { ScrollView, View, Text, StyleSheet } from 'react-native';
import { useStatsStore } from '../stores/stats';
import { useLibraryStore } from '../stores/library';
import { Header } from '../components/ui/Header';
import { colors, spacing, typography, borderRadius } from '../constants/theme';

// ─── Avatar ────────────────────────────────────────────────────────────────

function Avatar() {
  return (
    <View style={styles.avatarContainer}>
      <View style={styles.avatar}>
        <Text style={styles.avatarText}>YH</Text>
      </View>
      <Text style={styles.avatarSubtitle}>Local Reader</Text>
    </View>
  );
}

// ─── Stat card (2×2 grid item) ─────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: string | number;
  unit?: string;
}

function StatCard({ label, value, unit }: StatCardProps) {
  return (
    <View style={styles.statCard}>
      <Text style={styles.statLabel}>{label}</Text>
      <View style={styles.statValueRow}>
        <Text style={styles.statValue}>{value}</Text>
        {unit ? <Text style={styles.statUnit}>{unit}</Text> : null}
      </View>
    </View>
  );
}

// ─── Screen ────────────────────────────────────────────────────────────────

export default function ProfileScreen() {
  const { today, totalTimeToday, loadStats } = useStatsStore();
  const { downloadedBooks, loadDownloadedBooks } = useLibraryStore();

  useEffect(() => {
    loadStats();
    loadDownloadedBooks();
  }, []);

  // Derive hours read from today's time_seconds (cumulative for display purposes)
  const hoursReadDisplay = useMemo(() => {
    const h = Math.floor(today.time_seconds / 3600);
    const m = Math.floor((today.time_seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  }, [today.time_seconds]);

  // Books active: downloaded books with some progress but not complete
  const booksActive = useMemo(() => {
    return downloadedBooks.filter((b) => {
      if (b.page_count <= 0) return false;
      const pct = b.last_read_page / b.page_count;
      return pct > 0 && pct < 1;
    }).length;
  }, [downloadedBooks]);

  // Books completed: progress >= 1
  const booksCompleted = useMemo(() => {
    return downloadedBooks.filter((b) => {
      if (b.page_count <= 0) return false;
      return b.last_read_page / b.page_count >= 1;
    }).length;
  }, [downloadedBooks]);

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
    >
      <Header title="Profile" showBack />

      <Avatar />

      {/* Reading Stats */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Reading Stats</Text>
        <View style={styles.card}>
          <View style={styles.grid}>
            <StatCard label="TIME READ" value={hoursReadDisplay} />
            <StatCard label="BOOKS ACTIVE" value={booksActive} />
            <StatCard label="COMPLETED" value={booksCompleted} />
            <StatCard label="WORDS LEARNED" value={today.words_learned} />
          </View>
        </View>
      </View>

      {/* Today's activity summary */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Today</Text>
        <View style={styles.card}>
          <View style={styles.todayRow}>
            <View style={styles.todayItem}>
              <Text style={styles.todayValue}>{today.pages_read}</Text>
              <Text style={styles.todayLabel}>Pages Read</Text>
            </View>
            <View style={styles.todayDivider} />
            <View style={styles.todayItem}>
              <Text style={styles.todayValue}>{today.words_learned}</Text>
              <Text style={styles.todayLabel}>Words Learned</Text>
            </View>
            <View style={styles.todayDivider} />
            <View style={styles.todayItem}>
              <Text style={styles.todayValue}>{totalTimeToday}</Text>
              <Text style={styles.todayLabel}>Time Read</Text>
            </View>
          </View>
        </View>
      </View>

      <View style={styles.bottomPad} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    gap: spacing.lg,
    paddingBottom: spacing.xxl,
  },

  // Avatar
  avatarContainer: {
    alignItems: 'center',
    paddingTop: spacing.md,
    gap: spacing.sm,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarText: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.white,
    fontFamily: 'DMSans-Bold',
  },
  avatarSubtitle: {
    ...typography.caption,
    fontFamily: 'DMSans',
    color: colors.textSecondary,
  },

  // Section
  section: {
    paddingHorizontal: spacing.screenPadding,
    gap: spacing.sm,
  },
  sectionTitle: {
    ...typography.label,
    color: colors.textSecondary,
    fontFamily: 'DMSans-Medium',
  },
  card: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    overflow: 'hidden',
  },

  // 2x2 stats grid
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  statCard: {
    width: '50%',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderRightWidth: 1,
    borderBottomWidth: 1,
    borderColor: colors.cardBorder,
  },
  statLabel: {
    ...typography.statLabel,
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  statValueRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 2,
  },
  statValue: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.textPrimary,
    fontFamily: 'DMSans-Bold',
    lineHeight: 34,
  },
  statUnit: {
    fontSize: 13,
    fontWeight: '500',
    color: colors.textSecondary,
    marginBottom: 4,
    fontFamily: 'DMSans',
  },

  // Today row
  todayRow: {
    flexDirection: 'row',
    paddingVertical: spacing.md,
  },
  todayItem: {
    flex: 1,
    alignItems: 'center',
    gap: spacing.xs,
  },
  todayDivider: {
    width: 1,
    backgroundColor: colors.cardBorder,
    marginVertical: spacing.xs,
  },
  todayValue: {
    ...typography.h2,
    fontFamily: 'DMSans-SemiBold',
    color: colors.textPrimary,
  },
  todayLabel: {
    ...typography.caption,
    fontFamily: 'DMSans',
    color: colors.textSecondary,
  },

  bottomPad: { height: spacing.xl },
});
