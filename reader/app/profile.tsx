import { useEffect, useMemo } from 'react';
import { ScrollView, View, Text, Pressable, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { useStatsStore } from '../stores/stats';
import { useLibraryStore } from '../stores/library';
import { Header } from '../components/ui/Header';
import { Icon, IconName } from '../components/ui/Icon';
import { colors, spacing, typography, borderRadius } from '../constants/theme';

function Avatar() {
  return (
    <View style={styles.avatarContainer}>
      <View style={styles.avatar}>
        <Text style={styles.avatarText}>YH</Text>
      </View>
      <Text style={styles.fullName}>Yousef Hassan</Text>
      <Text style={styles.email}>yousef@example.com</Text>
    </View>
  );
}

function StatsBar({ hoursRead, booksActive, completed, wordsLearned }: {
  hoursRead: string; booksActive: number; completed: number; wordsLearned: string;
}) {
  const stats = [
    { label: 'HOURS READ', value: hoursRead },
    { label: 'BOOKS ACTIVE', value: booksActive },
    { label: 'COMPLETED', value: completed },
    { label: 'WORDS LEARNED', value: wordsLearned },
  ];
  return (
    <View style={styles.statsCard}>
      {stats.map((s, i) => (
        <View key={s.label} style={[styles.statCol, i < stats.length - 1 && styles.statBorder]}>
          <Text style={styles.statValue}>{s.value}</Text>
          <Text style={styles.statLabel}>{s.label}</Text>
        </View>
      ))}
    </View>
  );
}

function SectionTitle({ title }: { title: string }) {
  return <Text style={styles.sectionTitle}>{title}</Text>;
}

function SettingsRow({ icon, label, value, onPress, destructive }: {
  icon: IconName; label: string; value?: string; onPress?: () => void; destructive?: boolean;
}) {
  return (
    <Pressable style={styles.settingsRow} onPress={onPress}>
      <Icon name={icon} size={18} color={destructive ? colors.error : colors.textSecondary} />
      <Text style={[styles.rowLabel, destructive && styles.destructiveLabel]}>{label}</Text>
      <View style={styles.rowRight}>
        {value ? <Text style={styles.rowValue}>{value}</Text> : null}
        <Icon name="chevron-right" size={16} color={colors.textTertiary} />
      </View>
    </Pressable>
  );
}

function RowDivider() {
  return <View style={styles.divider} />;
}

export default function ProfileScreen() {
  const router = useRouter();
  const { today, totalTimeToday, loadStats } = useStatsStore();
  const { downloadedBooks, loadDownloadedBooks } = useLibraryStore();

  useEffect(() => {
    loadStats();
    loadDownloadedBooks();
  }, []);

  const hoursReadDisplay = useMemo(() => {
    const h = Math.floor(today.time_seconds / 3600);
    return h > 0 ? `${h}` : '0';
  }, [today.time_seconds]);

  const booksActive = useMemo(() => {
    return downloadedBooks.filter((b) => {
      if (b.page_count <= 0) return false;
      const pct = b.last_read_page / b.page_count;
      return pct > 0 && pct < 1;
    }).length;
  }, [downloadedBooks]);

  const booksCompleted = useMemo(() => {
    return downloadedBooks.filter((b) => {
      if (b.page_count <= 0) return false;
      return b.last_read_page / b.page_count >= 1;
    }).length;
  }, [downloadedBooks]);

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <Header title="Profile" showBack />
      <Avatar />
      <View style={styles.section}>
        <StatsBar
          hoursRead={hoursReadDisplay}
          booksActive={booksActive}
          completed={booksCompleted}
          wordsLearned={today.words_learned > 999 ? `${(today.words_learned / 1000).toFixed(1)}k` : String(today.words_learned)}
        />
      </View>

      {/* SUBSCRIPTION */}
      <View style={styles.section}>
        <SectionTitle title="SUBSCRIPTION" />
        <View style={styles.card}>
          <View style={styles.subRow}>
            <Icon name="star" size={20} color={colors.accent} />
            <View style={styles.subInfo}>
              <View style={styles.subTitleRow}>
                <Text style={styles.subPlan}>Monthly Plan</Text>
                <View style={styles.activeBadge}>
                  <Text style={styles.activeBadgeText}>ACTIVE</Text>
                </View>
              </View>
              <Text style={styles.subPrice}>$7.99/month · Renews May 12, 2026</Text>
            </View>
            <Pressable><Text style={styles.manageText}>Manage</Text></Pressable>
          </View>
          <RowDivider />
          <View style={styles.upsellRow}>
            <Text style={styles.upsellText}>Save 37% with annual billing</Text>
            <Pressable><Text style={styles.switchText}>Switch to Annual</Text></Pressable>
          </View>
        </View>
      </View>

      {/* ACCOUNT */}
      <View style={styles.section}>
        <SectionTitle title="ACCOUNT" />
        <View style={styles.card}>
          <SettingsRow icon="user" label="Name" value="Yousef Hassan" />
          <RowDivider />
          <SettingsRow icon="mail" label="Email" value="yousef@example.com" />
        </View>
      </View>

      {/* SUPPORT */}
      <View style={styles.section}>
        <SectionTitle title="SUPPORT" />
        <View style={styles.card}>
          <SettingsRow icon="help-circle" label="Help Center" />
          <RowDivider />
          <SettingsRow icon="message-square" label="Contact Us" />
          <RowDivider />
          <SettingsRow icon="star" label="Rate Suhuf" />
        </View>
      </View>

      {/* Sign Out */}
      <View style={styles.section}>
        <Pressable style={styles.signOutButton}>
          <Text style={styles.signOutText}>Sign Out</Text>
        </Pressable>
      </View>

      {/* Version */}
      <Text style={styles.versionText}>Suhuf v2.1.0 · Build 847</Text>

      <View style={styles.bottomPad} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { gap: spacing.lg, paddingBottom: spacing.xxl },

  avatarContainer: { alignItems: 'center', paddingTop: spacing.lg, gap: spacing.xs },
  avatar: {
    width: 72, height: 72, borderRadius: 36,
    backgroundColor: colors.primary,
    justifyContent: 'center', alignItems: 'center',
    borderWidth: 2, borderColor: colors.cardBorder,
  },
  avatarText: { fontSize: 24, fontWeight: '700', color: colors.white, fontFamily: 'DMSans-Bold' },
  fullName: { fontFamily: 'DMSans-SemiBold', fontSize: 20, color: colors.textPrimary, marginTop: spacing.sm },
  email: { fontFamily: 'DMSans', fontSize: 14, color: colors.textSecondary },

  section: { paddingHorizontal: spacing.screenPadding, gap: spacing.sm },
  sectionTitle: { ...typography.label, fontFamily: 'DMSans-Medium', color: colors.textSecondary },

  card: {
    backgroundColor: colors.card, borderRadius: borderRadius.lg,
    borderWidth: 1, borderColor: colors.cardBorder, overflow: 'hidden',
  },
  divider: { height: 1, backgroundColor: colors.cardBorder, marginHorizontal: spacing.md },

  statsCard: {
    flexDirection: 'row', backgroundColor: colors.card, borderRadius: borderRadius.lg,
    borderWidth: 1, borderColor: colors.cardBorder, overflow: 'hidden',
  },
  statCol: { flex: 1, alignItems: 'center', paddingVertical: spacing.md, gap: spacing.xs },
  statBorder: { borderRightWidth: 1, borderRightColor: colors.cardBorder },
  statValue: { fontFamily: 'DMSans-Bold', fontSize: 22, color: colors.textPrimary },
  statLabel: { ...typography.statLabel, fontFamily: 'DMSans-Medium', color: colors.textSecondary },

  subRow: { flexDirection: 'row', alignItems: 'center', padding: spacing.md, gap: spacing.sm },
  subInfo: { flex: 1, gap: 2 },
  subTitleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  subPlan: { fontFamily: 'DMSans-SemiBold', fontSize: 15, color: colors.textPrimary },
  activeBadge: {
    backgroundColor: colors.success, borderRadius: borderRadius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 2,
  },
  activeBadgeText: { fontFamily: 'DMSans-Bold', fontSize: 10, color: colors.white, letterSpacing: 0.5 },
  subPrice: { fontFamily: 'DMSans', fontSize: 13, color: colors.textSecondary },
  manageText: { fontFamily: 'DMSans-SemiBold', fontSize: 14, color: colors.accent },

  upsellRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  upsellText: { fontFamily: 'DMSans', fontSize: 13, color: colors.textSecondary },
  switchText: { fontFamily: 'DMSans-SemiBold', fontSize: 14, color: colors.accent },

  settingsRow: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  rowLabel: { flex: 1, fontFamily: 'DMSans', fontSize: 15, color: colors.textPrimary },
  rowRight: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  rowValue: { fontFamily: 'DMSans', fontSize: 14, color: colors.textSecondary },
  destructiveLabel: { color: colors.error },

  signOutButton: {
    backgroundColor: colors.card, borderRadius: borderRadius.lg,
    borderWidth: 1, borderColor: colors.cardBorder,
    paddingVertical: spacing.md, alignItems: 'center',
  },
  signOutText: { fontFamily: 'DMSans-SemiBold', fontSize: 15, color: colors.error },
  versionText: {
    fontFamily: 'DMSans', fontSize: 12, color: colors.textTertiary,
    textAlign: 'center', paddingTop: spacing.sm,
  },

  bottomPad: { height: spacing.xl },
});
