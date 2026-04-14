import { View, Text, Pressable, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import type { DownloadedBook } from '../../types';
import { colors, spacing, borderRadius, typography } from '../../constants/theme';
import { ProgressBar } from '../ui/ProgressBar';

interface ContinueReadingProps {
  books: DownloadedBook[];
  progress: Record<string, number>; // book_id -> 0-1
}

function BookRow({
  book,
  progress,
  showResume,
}: {
  book: DownloadedBook;
  progress: number;
  showResume: boolean;
}) {
  const router = useRouter();
  const pct = Math.round(progress * 100);

  return (
    <View style={styles.row}>
      {/* Cover thumbnail */}
      <View style={[styles.cover, { backgroundColor: book.cover_color }]}>
        <Text style={styles.coverText}>{book.title_ar}</Text>
      </View>

      {/* Info center */}
      <View style={styles.info}>
        <Text style={styles.bookTitle} numberOfLines={1}>
          {book.title_en}
        </Text>
        <Text style={styles.author} numberOfLines={1}>
          {book.author_en ?? book.author_ar} · {book.category}
        </Text>
        <View style={styles.progressRow}>
          <ProgressBar progress={progress} />
          <Text style={styles.pct}>{pct}%</Text>
        </View>
      </View>

      {/* Resume button — first book only */}
      {showResume && (
        <Pressable
          style={styles.resumeButton}
          onPress={() => router.push(`/book/${book.id}`)}
        >
          <Text style={styles.resumeText}>Resume</Text>
        </Pressable>
      )}
    </View>
  );
}

export function ContinueReading({ books, progress }: ContinueReadingProps) {
  if (books.length === 0) return null;

  return (
    <View style={styles.container}>
      {books.slice(0, 3).map((book, index) => (
        <BookRow
          key={book.id}
          book={book}
          progress={progress[book.id] ?? 0}
          showResume={index === 0}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: spacing.screenPadding,
    gap: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    padding: spacing.md,
    gap: spacing.md,
  },
  cover: {
    width: 56,
    height: 72,
    borderRadius: borderRadius.sm,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  coverText: {
    fontSize: 12,
    color: '#FFFFFF',
    textAlign: 'center',
    paddingHorizontal: 2,
  },
  info: {
    flex: 1,
    gap: 4,
  },
  bookTitle: {
    fontFamily: 'DMSans-SemiBold',
    fontSize: 16,
    color: colors.textPrimary,
    lineHeight: 22,
  },
  author: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  progressRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: 4,
  },
  pct: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.accent,
    minWidth: 32,
  },
  resumeButton: {
    backgroundColor: colors.primary,
    borderRadius: borderRadius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  resumeText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#FFFFFF',
  },
});
