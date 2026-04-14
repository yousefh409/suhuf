import { View, StyleSheet } from 'react-native';
import type { Block, Token } from '../../types';
import { ArabicWord } from './ArabicWord';
import { colors, spacing, borderRadius } from '../../constants/theme';
import { useReaderStore } from '../../stores/reader';

interface ArabicBlockProps {
  block: Block;
}

/** Build a sentence string from all tokens in the block. */
function buildSentence(tokens: Token[]): string {
  return tokens.map((t) => t.text).join(' ');
}

export function ArabicBlock({ block }: ArabicBlockProps) {
  const selectedToken = useReaderStore((s) => s.selectedToken);
  const sentence = buildSentence(block.tokens);

  return (
    <View style={[styles.block, blockStyles[block.type] ?? {}]}>
      <View style={styles.tokensRow}>
        {block.tokens.map((token) => (
          <ArabicWord
            key={token.id}
            token={token}
            sentence={sentence}
            isSelected={selectedToken?.id === token.id}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  block: {
    marginBottom: spacing.md,
  },
  tokensRow: {
    flexDirection: 'row-reverse',
    flexWrap: 'wrap',
    justifyContent: 'flex-start',
  },
});

const blockStyles = StyleSheet.create({
  prose: {},
  hadith: {
    backgroundColor: '#F0E8D8',
    borderLeftWidth: 3,
    borderLeftColor: colors.accent,
    borderRadius: borderRadius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  isnad: {
    backgroundColor: '#EEE8DC',
    borderRadius: borderRadius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  matn: {
    backgroundColor: '#F5F0E8',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.sm,
  },
  poetry: {
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: colors.cardBorder,
  },
  biography: {
    paddingHorizontal: spacing.md,
  },
  heading: {
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
    paddingBottom: spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: colors.cardBorder,
  },
});
