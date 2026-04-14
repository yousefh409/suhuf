import { ScrollView, View, Text, Pressable, Switch, StyleSheet } from 'react-native';
import { useSettingsStore } from '../stores/settings';
import { Header } from '../components/ui/Header';
import { Icon, IconName } from '../components/ui/Icon';
import { colors, spacing, typography, borderRadius } from '../constants/theme';

function SectionTitle({ title }: { title: string }) {
  return <Text style={styles.sectionTitle}>{title}</Text>;
}

function RowDivider() {
  return <View style={styles.divider} />;
}

function SettingsRow({ icon, label, value, onPress, destructive }: {
  icon: IconName; label: string; value?: string; onPress?: () => void; destructive?: boolean;
}) {
  return (
    <Pressable style={styles.row} onPress={onPress}>
      <Icon name={icon} size={18} color={destructive ? colors.error : colors.textSecondary} />
      <Text style={[styles.rowLabel, destructive && styles.destructiveText]}>{label}</Text>
      <View style={styles.rowRight}>
        {value ? <Text style={styles.rowValue}>{value}</Text> : null}
        <Icon name="chevron-right" size={16} color={colors.textTertiary} />
      </View>
    </Pressable>
  );
}

function ToggleRow({ icon, label, value, onToggle }: {
  icon: IconName; label: string; value: boolean; onToggle: () => void;
}) {
  return (
    <View style={styles.row}>
      <Icon name={icon} size={18} color={colors.textSecondary} />
      <Text style={styles.rowLabel}>{label}</Text>
      <Switch
        value={value}
        onValueChange={onToggle}
        trackColor={{ false: colors.cardBorder, true: colors.accent }}
        thumbColor={colors.white}
      />
    </View>
  );
}

const FONT_SIZE_LABELS: Record<number, string> = {
  18: 'Small', 20: 'Small', 22: 'Medium', 24: 'Large', 26: 'Large', 28: 'X-Large', 30: 'X-Large', 32: 'X-Large',
};

export default function SettingsScreen() {
  const {
    fontSize, arabicFont, aiLanguage, grammarDetail, notificationsEnabled,
    setFontSize, setArabicFont, setAiLanguage, setGrammarDetail, toggleNotifications,
  } = useSettingsStore();

  const fontSizeLabel = FONT_SIZE_LABELS[fontSize] ?? `${fontSize}`;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <Header title="Settings" showBack backLabel="Profile" />

      {/* READING */}
      <View style={styles.section}>
        <SectionTitle title="READING" />
        <View style={styles.card}>
          <SettingsRow icon="type" label="Font Size" value={fontSizeLabel} />
          <RowDivider />
          <SettingsRow icon="smartphone" label="Arabic Font" value={arabicFont} />
        </View>
      </View>

      {/* AI ASSISTANT */}
      <View style={styles.section}>
        <SectionTitle title="AI ASSISTANT" />
        <View style={styles.card}>
          <SettingsRow icon="message-square" label="Explanation Language" value={aiLanguage} />
          <RowDivider />
          <SettingsRow icon="list" label="Grammar Detail Level" value={grammarDetail} />
        </View>
      </View>

      {/* NOTIFICATIONS */}
      <View style={styles.section}>
        <SectionTitle title="NOTIFICATIONS" />
        <View style={styles.card}>
          <ToggleRow icon="bell" label="Daily Reading Reminder" value={notificationsEnabled} onToggle={toggleNotifications} />
          <RowDivider />
          <SettingsRow icon="clock" label="Reminder Time" value="8:00 AM" />
        </View>
      </View>

      {/* DATA & PRIVACY */}
      <View style={styles.section}>
        <SectionTitle title="DATA & PRIVACY" />
        <View style={styles.card}>
          <SettingsRow icon="upload-cloud" label="Export Reading Data" />
          <RowDivider />
          <SettingsRow icon="trash-2" label="Delete Account" destructive />
        </View>
      </View>

      <View style={styles.bottomPad} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { gap: spacing.lg, paddingBottom: spacing.xxl },

  section: { paddingHorizontal: spacing.screenPadding, gap: spacing.sm },
  sectionTitle: { ...typography.label, fontFamily: 'DMSans-Medium', color: colors.textSecondary },

  card: {
    backgroundColor: colors.card, borderRadius: borderRadius.lg,
    borderWidth: 1, borderColor: colors.cardBorder, overflow: 'hidden',
  },
  divider: { height: 1, backgroundColor: colors.cardBorder, marginHorizontal: spacing.md },

  row: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  rowLabel: { flex: 1, fontFamily: 'DMSans', fontSize: 15, color: colors.textPrimary },
  rowRight: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  rowValue: { fontFamily: 'DMSans', fontSize: 14, color: colors.textSecondary },
  destructiveText: { color: colors.error },

  bottomPad: { height: spacing.xl },
});
