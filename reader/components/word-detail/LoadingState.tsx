import { View, StyleSheet, Animated } from 'react-native';
import { useEffect, useRef } from 'react';
import { colors, borderRadius, spacing } from '../../constants/theme';

function SkeletonLine({ width, height = 14 }: { width: number | string; height?: number }) {
  const opacity = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 1, duration: 800, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.4, duration: 800, useNativeDriver: true }),
      ])
    );
    animation.start();
    return () => animation.stop();
  }, []);

  return (
    <Animated.View
      style={[
        styles.skeletonLine,
        { width: width as any, height, opacity },
      ]}
    />
  );
}

export function LoadingState() {
  return (
    <View style={styles.container}>
      {/* Word header skeleton */}
      <View style={styles.wordRow}>
        <SkeletonLine width={120} height={36} />
        <SkeletonLine width={80} height={16} />
      </View>

      {/* Tags row */}
      <View style={styles.tagsRow}>
        <SkeletonLine width={60} height={28} />
        <SkeletonLine width={80} height={28} />
        <SkeletonLine width={50} height={28} />
      </View>

      {/* Content card */}
      <View style={styles.card}>
        <SkeletonLine width="90%" />
        <SkeletonLine width="75%" />
        <SkeletonLine width="85%" />
        <SkeletonLine width="60%" />
      </View>

      {/* Related words label */}
      <SkeletonLine width={100} height={12} />

      {/* Related word rows */}
      <View style={styles.relatedRow}>
        <SkeletonLine width={70} height={20} />
        <SkeletonLine width={100} height={14} />
      </View>
      <View style={styles.relatedRow}>
        <SkeletonLine width={80} height={20} />
        <SkeletonLine width={90} height={14} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    gap: spacing.md,
    paddingTop: spacing.sm,
  },
  wordRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  tagsRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    flexWrap: 'wrap',
  },
  card: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    padding: spacing.md,
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: colors.cardBorder,
  },
  skeletonLine: {
    backgroundColor: colors.cardBorder,
    borderRadius: borderRadius.sm,
  },
  relatedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: colors.cardBorder,
  },
});
