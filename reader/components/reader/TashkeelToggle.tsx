import { Pressable, Text, StyleSheet } from 'react-native';
import { useReaderStore } from '../../stores/reader';
import { Icon } from '../ui/Icon';
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
      <Icon
        name={showTashkeel ? 'eye' : 'eye-off'}
        size={16}
        color={showTashkeel ? colors.white : colors.textSecondary}
      />
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
  label: {
    fontFamily: 'DMSans-Medium',
    fontSize: 13,
    color: colors.textSecondary,
  },
  labelActive: {
    color: colors.white,
  },
});
