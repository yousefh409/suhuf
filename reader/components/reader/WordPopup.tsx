import { View, Text, Pressable, StyleSheet } from 'react-native';
import { useReaderStore } from '../../stores/reader';
import { colors, spacing, borderRadius } from '../../constants/theme';

export function WordPopup() {
  const showWordPopup = useReaderStore((s) => s.showWordPopup);
  const wordPopupPosition = useReaderStore((s) => s.wordPopupPosition);
  const openGrammar = useReaderStore((s) => s.openGrammar);
  const openTranslation = useReaderStore((s) => s.openTranslation);
  const clearSelection = useReaderStore((s) => s.clearSelection);

  if (!showWordPopup || !wordPopupPosition) return null;

  // Position the popup above the tapped word
  const popupTop = wordPopupPosition.y - 60;
  const popupLeft = Math.max(8, wordPopupPosition.x - 120);

  return (
    <View
      style={[styles.container, { top: popupTop, left: popupLeft }]}
      pointerEvents="box-none"
    >
      {/* Grammar button */}
      <Pressable
        style={styles.button}
        onPress={openGrammar}
        accessibilityRole="button"
        accessibilityLabel="View grammar"
      >
        <Text style={styles.buttonIcon}>✏</Text>
        <Text style={styles.buttonText}>Grammar</Text>
      </Pressable>

      <View style={styles.divider} />

      {/* Translate button */}
      <Pressable
        style={styles.button}
        onPress={openTranslation}
        accessibilityRole="button"
        accessibilityLabel="Translate"
      >
        <Text style={styles.buttonIcon}>⟳</Text>
        <Text style={styles.buttonText}>Translate</Text>
      </Pressable>

      <View style={styles.divider} />

      {/* Copy / dismiss */}
      <Pressable
        style={styles.button}
        onPress={clearSelection}
        accessibilityRole="button"
        accessibilityLabel="Dismiss"
      >
        <Text style={styles.buttonIcon}>✕</Text>
      </Pressable>

      {/* Arrow pointing down */}
      <View style={styles.arrow} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: borderRadius.md,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 12,
    elevation: 8,
    zIndex: 200,
  },
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
  },
  buttonIcon: {
    fontSize: 13,
    color: colors.white,
  },
  buttonText: {
    fontFamily: 'DMSans-Medium',
    fontSize: 14,
    color: colors.white,
  },
  divider: {
    width: 1,
    height: 20,
    backgroundColor: 'rgba(255,255,255,0.25)',
  },
  arrow: {
    position: 'absolute',
    bottom: -8,
    left: '50%',
    marginLeft: -8,
    width: 0,
    height: 0,
    borderLeftWidth: 8,
    borderRightWidth: 8,
    borderTopWidth: 8,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    borderTopColor: colors.primary,
  },
});
