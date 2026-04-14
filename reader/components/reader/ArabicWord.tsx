import { useRef } from 'react';
import { Text, Pressable, StyleSheet, View } from 'react-native';
import type { Token } from '../../types';
import { useSettingsStore } from '../../stores/settings';
import { useReaderStore } from '../../stores/reader';
import { colors } from '../../constants/theme';

/** Strip Arabic diacritical marks (tashkeel) from text. */
function stripTashkeel(text: string): string {
  return text.replace(/[\u064B-\u065F\u0670]/g, '');
}

interface ArabicWordProps {
  token: Token;
  sentence: string;
  isSelected?: boolean;
}

export function ArabicWord({ token, sentence, isSelected }: ArabicWordProps) {
  const { fontSize, arabicFont, showTashkeel } = useSettingsStore();
  const showTashkeelFromReader = useReaderStore((s) => s.showTashkeel);
  const selectWord = useReaderStore((s) => s.selectWord);

  // Use the reader store's tashkeel toggle (overrides settings during session)
  const displayTashkeel = showTashkeelFromReader && showTashkeel;
  // Diacritics are embedded in token.text; strip them when tashkeel is off
  const displayText = displayTashkeel
    ? (token.tashkeel || token.text)
    : stripTashkeel(token.text);

  const ref = useRef<View>(null);

  const handlePress = () => {
    ref.current?.measure((_x, _y, _w, _h, pageX, pageY) => {
      selectWord(token, sentence, { x: pageX, y: pageY });
    });
  };

  return (
    <Pressable ref={ref as any} onPress={handlePress} style={styles.pressable}>
      <Text
        style={[
          styles.word,
          { fontSize, fontFamily: mapFont(arabicFont) },
          isSelected && styles.selected,
        ]}
      >
        {displayText}
      </Text>
    </Pressable>
  );
}

/** Map the ArabicFont setting value to the loaded font family name. */
function mapFont(arabicFont: string): string {
  switch (arabicFont) {
    case 'Amiri':
      return 'Amiri';
    case 'Scheherazade New':
      return 'ScheherazadeNew';
    default:
      return 'NotoNaskhArabic';
  }
}

const styles = StyleSheet.create({
  pressable: {
    marginHorizontal: 2,
  },
  word: {
    color: colors.textPrimary,
    lineHeight: 56,
    writingDirection: 'rtl',
    textAlign: 'right',
  },
  selected: {
    color: colors.accent,
    textDecorationLine: 'underline',
    textDecorationColor: colors.accent,
  },
});
