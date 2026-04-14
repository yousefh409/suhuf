import { Pressable, Text, StyleSheet, View } from 'react-native';
import { useReaderStore } from '../../stores/reader';
import { colors, borderRadius, spacing } from '../../constants/theme';

export function TashkeelToggle() {
  const showTashkeel = useReaderStore((s) => s.showTashkeel);
  const toggleTashkeel = useReaderStore((s) => s.toggleTashkeel);

  return (
    <Pressable
      onPress={toggleTashkeel}
      style={[styles.button, showTashkeel && styles.buttonActive]}
      accessibilityRole="switch"
      accessibilityState={{ checked: showTashkeel }}
      accessibilityLabel="Toggle diacritics"
    >
      {/* Eye icon SVG approximation using unicode */}
      <Text style={[styles.icon, showTashkeel && styles.iconActive]}>
        {showTashkeel ? '👁' : '🙈'}
      </Text>
      <Text style={[styles.label, showTashkeel && styles.labelActive]}>
        Tashkeel
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.full,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.cardBorder,
  },
  buttonActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  icon: {
    fontSize: 14,
  },
  iconActive: {},
  label: {
    fontFamily: 'DMSans-Medium',
    fontSize: 13,
    color: colors.textSecondary,
  },
  labelActive: {
    color: colors.white,
  },
});
