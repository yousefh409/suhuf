import { View, Text, Pressable, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import type { Book, DownloadedBook } from '../../types';
import { colors, typography, spacing, borderRadius } from '../../constants/theme';
import { ProgressBar } from '../ui/ProgressBar';

interface BookCardProps {
  book: Book | DownloadedBook;
  variant?: 'large' | 'medium' | 'small';
  progress?: number; // 0-1, only for downloaded books
  onPress?: () => void;
}

export function BookCard({ book, variant = 'medium', progress, onPress }: BookCardProps) {
  const router = useRouter();

  const handlePress = () => {
    if (onPress) {
      onPress();
    } else {
      router.push(`/book/${book.id}`);
    }
  };

  return (
    <Pressable style={[styles.container, variantStyles[variant]]} onPress={handlePress}>
      {/* Book cover */}
      <View style={[styles.cover, variantCoverStyles[variant], { backgroundColor: book.cover_color }]}>
        <Text style={[styles.coverText, variant === 'small' && styles.coverTextSmall]}>
          {book.title_ar}
        </Text>
        {progress !== undefined && progress > 0 && (
          <View style={styles.progressBadge}>
            <Text style={styles.progressBadgeText}>{Math.round(progress * 100)}%</Text>
          </View>
        )}
      </View>

      {/* Book info */}
      <Text style={[styles.title, variant === 'small' && styles.titleSmall]} numberOfLines={2}>
        {book.title_en}
      </Text>
      <Text style={styles.author} numberOfLines={1}>
        {book.author_en ?? book.author_ar}
      </Text>

      {/* Progress bar for downloaded books */}
      {progress !== undefined && (
        <View style={styles.progressContainer}>
          <ProgressBar progress={progress} />
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {},
  cover: {
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  coverText: {
    fontFamily: 'NotoNaskhArabic-Bold',
    fontSize: 18,
    color: '#FFFFFF',
    textAlign: 'center',
    paddingHorizontal: spacing.sm,
  },
  coverTextSmall: { fontSize: 14 },
  progressBadge: {
    position: 'absolute',
    top: spacing.xs,
    right: spacing.xs,
    backgroundColor: colors.accent,
    borderRadius: borderRadius.full,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  progressBadgeText: { fontFamily: 'DMSans-SemiBold', fontSize: 11, color: '#FFFFFF' },
  title: { fontFamily: 'DMSans-SemiBold', fontSize: 14, color: colors.textPrimary, marginTop: spacing.sm },
  titleSmall: { fontSize: 13 },
  author: { fontFamily: 'DMSans', fontSize: 12, color: colors.textSecondary, marginTop: 2 },
  progressContainer: { marginTop: spacing.sm },
});

const variantStyles: Record<string, object> = {
  large: { width: '100%' },
  medium: { width: 170 },
  small: { width: 140 },
};

const variantCoverStyles: Record<string, object> = {
  large: { width: '100%', height: 100 },
  medium: { width: 170, height: 110 },
  small: { width: 140, height: 90 },
};
