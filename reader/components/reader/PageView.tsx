import { ScrollView, StyleSheet, View } from 'react-native';
import type { Page } from '../../types';
import { ArabicBlock } from './ArabicBlock';
import { colors, spacing } from '../../constants/theme';
import { useSettingsStore } from '../../stores/settings';

interface PageViewProps {
  page: Page;
  width: number;
}

export function PageView({ page, width }: PageViewProps) {
  const { fontSize } = useSettingsStore();

  // Scale line height based on user font size preference
  const lineHeightScale = fontSize / 24;

  return (
    <View style={[styles.container, { width }]}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        bounces={false}
      >
        {page.blocks.map((block, index) => (
          <View
            key={`${page.id}_block_${index}`}
            style={[
              styles.blockWrapper,
              block.type === 'heading' && styles.headingWrapper,
            ]}
          >
            <ArabicBlock block={block} />
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scroll: {
    flex: 1,
  },
  content: {
    paddingHorizontal: spacing.screenPadding,
    paddingTop: spacing.md,
    paddingBottom: spacing.xl,
  },
  blockWrapper: {
    marginBottom: spacing.xs,
  },
  headingWrapper: {
    marginTop: spacing.lg,
  },
});
