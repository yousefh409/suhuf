import { useCallback } from 'react';
import { ScrollView, View, Text, Pressable, Switch, StyleSheet, Alert } from 'react-native';
import { useSettingsStore } from '../stores/settings';
import { Header } from '../components/ui/Header';
import { colors, spacing, typography, borderRadius } from '../constants/theme';
import type { ArabicFont, AiLanguage, GrammarDetail } from '../types';

// ─── Section wrapper ───────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <View style={styles.card}>{children}</View>
    </View>
  );
}

// ─── Row components ────────────────────────────────────────────────────────

function RowDivider() {
  return <View style={styles.divider} />;
}

function LabelRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={styles.rowRight}>{children}</View>
    </View>
  );
}

// ─── Radio group ───────────────────────────────────────────────────────────

function RadioGroup<T extends string>({
  options,
  value,
  onChange,
}: {
  options: T[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <View style={styles.radioGroup}>
      {options.map((opt, i) => (
        <Pressable
          key={opt}
          onPress={() => onChange(opt)}
          style={[
            styles.radioOption,
            value === opt && styles.radioOptionActive,
            i === 0 && styles.radioFirst,
            i === options.length - 1 && styles.radioLast,
          ]}
        >
          <Text
            style={[
              styles.radioLabel,
              value === opt && styles.radioLabelActive,
            ]}
          >
            {opt}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

// ─── Destructive button ────────────────────────────────────────────────────

function DestructiveRow({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.row, pressed && styles.pressed]}>
      <Text style={styles.destructiveLabel}>{label}</Text>
    </Pressable>
  );
}

// ─── Screen ────────────────────────────────────────────────────────────────

const ARABIC_FONTS: ArabicFont[] = ['Noto Naskh Arabic', 'Amiri', 'Scheherazade New'];
const AI_LANGUAGES: AiLanguage[] = ['English', 'Arabic'];
const GRAMMAR_LEVELS: GrammarDetail[] = ['Simple', 'Detailed', 'Expert'];

export default function SettingsScreen() {
  const {
    fontSize,
    arabicFont,
    aiLanguage,
    grammarDetail,
    notificationsEnabled,
    setFontSize,
    setArabicFont,
    setAiLanguage,
    setGrammarDetail,
    toggleNotifications,
  } = useSettingsStore();

  const handleClearCache = useCallback(() => {
    Alert.alert('Clear Cache', 'Remove all cached data?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Clear', style: 'destructive', onPress: () => { /* no-op in Phase 1 */ } },
    ]);
  }, []);

  const handleClearHistory = useCallback(() => {
    Alert.alert('Clear Reading History', 'This will remove all reading progress. This cannot be undone.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Clear', style: 'destructive', onPress: () => { /* no-op in Phase 1 */ } },
    ]);
  }, []);

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
    >
      <Header title="Settings" showBack />

      {/* Reading */}
      <Section title="Reading">
        {/* Font size */}
        <View style={styles.sliderRow}>
          <View style={styles.sliderHeader}>
            <Text style={styles.rowLabel}>Font Size</Text>
            <View style={styles.stepper}>
              <Pressable
                onPress={() => setFontSize(Math.max(18, fontSize - 1))}
                style={({ pressed }) => [styles.stepBtn, pressed && styles.pressed]}
                disabled={fontSize <= 18}
              >
                <Text style={[styles.stepIcon, fontSize <= 18 && styles.stepDisabled]}>−</Text>
              </Pressable>
              <Text style={styles.sliderValue}>{fontSize}</Text>
              <Pressable
                onPress={() => setFontSize(Math.min(32, fontSize + 1))}
                style={({ pressed }) => [styles.stepBtn, pressed && styles.pressed]}
                disabled={fontSize >= 32}
              >
                <Text style={[styles.stepIcon, fontSize >= 32 && styles.stepDisabled]}>+</Text>
              </Pressable>
            </View>
          </View>
          {/* Live preview */}
          <Text
            style={[styles.arabicPreview, { fontSize, fontFamily: arabicFont === 'Noto Naskh Arabic' ? 'NotoNaskhArabic' : arabicFont === 'Amiri' ? 'Amiri' : 'ScheherazadeNew' }]}
            numberOfLines={1}
          >
            بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ
          </Text>
        </View>

        <RowDivider />

        {/* Arabic font */}
        <View style={styles.fontSection}>
          <Text style={styles.rowLabel}>Arabic Font</Text>
          <View style={styles.fontOptions}>
            {ARABIC_FONTS.map((font) => (
              <Pressable
                key={font}
                onPress={() => setArabicFont(font)}
                style={[styles.fontOption, arabicFont === font && styles.fontOptionActive]}
              >
                <Text
                  style={[
                    styles.fontOptionArabic,
                    {
                      fontFamily:
                        font === 'Noto Naskh Arabic'
                          ? 'NotoNaskhArabic'
                          : font === 'Amiri'
                          ? 'Amiri'
                          : 'ScheherazadeNew',
                    },
                    arabicFont === font && styles.fontOptionTextActive,
                  ]}
                >
                  بسم الله
                </Text>
                <Text style={[styles.fontOptionName, arabicFont === font && styles.fontOptionTextActive]}>
                  {font}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
      </Section>

      {/* AI Assistant */}
      <Section title="AI Assistant">
        <LabelRow label="Language">
          <RadioGroup
            options={AI_LANGUAGES}
            value={aiLanguage}
            onChange={setAiLanguage}
          />
        </LabelRow>

        <RowDivider />

        <View style={styles.grammarRow}>
          <Text style={styles.rowLabel}>Grammar Detail Level</Text>
          <RadioGroup
            options={GRAMMAR_LEVELS}
            value={grammarDetail}
            onChange={setGrammarDetail}
          />
        </View>
      </Section>

      {/* Notifications */}
      <Section title="Notifications">
        <LabelRow label="Enable Notifications">
          <Switch
            value={notificationsEnabled}
            onValueChange={toggleNotifications}
            trackColor={{ false: colors.cardBorder, true: colors.accent }}
            thumbColor={colors.white}
          />
        </LabelRow>
      </Section>

      {/* Data & Privacy */}
      <Section title="Data & Privacy">
        <DestructiveRow label="Clear Cache" onPress={handleClearCache} />
        <RowDivider />
        <DestructiveRow label="Clear Reading History" onPress={handleClearHistory} />
      </Section>

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

  // Rows
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  rowLabel: {
    ...typography.body,
    fontFamily: 'DMSans',
    color: colors.textPrimary,
  },
  rowRight: {
    flexShrink: 0,
  },
  divider: {
    height: 1,
    backgroundColor: colors.cardBorder,
    marginHorizontal: spacing.md,
  },
  pressed: {
    opacity: 0.6,
  },

  // Font size stepper
  sliderRow: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
    gap: spacing.sm,
  },
  sliderHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sliderValue: {
    ...typography.body,
    fontFamily: 'DMSans-SemiBold',
    color: colors.accent,
    minWidth: 28,
    textAlign: 'center',
  },
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: borderRadius.sm,
    overflow: 'hidden',
  },
  stepBtn: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    backgroundColor: colors.background,
  },
  stepIcon: {
    fontSize: 20,
    color: colors.textPrimary,
    fontFamily: 'DMSans',
    lineHeight: 24,
  },
  stepDisabled: {
    color: colors.textTertiary,
  },
  arabicPreview: {
    color: colors.textPrimary,
    textAlign: 'right',
  },

  // Font picker
  fontSection: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
    gap: spacing.sm,
  },
  fontOptions: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  fontOption: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: borderRadius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
    alignItems: 'center',
    gap: 4,
  },
  fontOptionActive: {
    borderColor: colors.accent,
    backgroundColor: '#FBF7F0',
  },
  fontOptionArabic: {
    fontSize: 20,
    color: colors.textPrimary,
  },
  fontOptionName: {
    fontSize: 10,
    fontFamily: 'DMSans',
    color: colors.textSecondary,
    textAlign: 'center',
  },
  fontOptionTextActive: {
    color: colors.accent,
  },

  // Grammar row (full-width radio below label)
  grammarRow: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
    gap: spacing.sm,
  },

  // Radio group
  radioGroup: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: borderRadius.sm,
    overflow: 'hidden',
  },
  radioOption: {
    flex: 1,
    paddingVertical: spacing.xs + 2,
    paddingHorizontal: spacing.xs,
    alignItems: 'center',
    backgroundColor: colors.white,
    borderRightWidth: 1,
    borderRightColor: colors.cardBorder,
  },
  radioFirst: {},
  radioLast: {
    borderRightWidth: 0,
  },
  radioOptionActive: {
    backgroundColor: colors.primary,
  },
  radioLabel: {
    ...typography.caption,
    fontFamily: 'DMSans',
    color: colors.textSecondary,
  },
  radioLabelActive: {
    color: colors.white,
    fontFamily: 'DMSans-Medium',
  },

  // Destructive
  destructiveLabel: {
    ...typography.body,
    fontFamily: 'DMSans',
    color: colors.error,
  },

  bottomPad: { height: spacing.xl },
});
