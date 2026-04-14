import { View, StyleSheet, useWindowDimensions } from 'react-native';
import type { Book, DownloadedBook } from '../../types';
import { spacing } from '../../constants/theme';
import { BookCard } from './BookCard';

interface BookGridProps {
  books: Array<Book | DownloadedBook>;
  progressMap?: Record<string, number>;
  maxRows?: number;
}

export function BookGrid({ books, progressMap = {}, maxRows }: BookGridProps) {
  const { width } = useWindowDimensions();

  // 5 columns on iPad (width >= 768), else 3 columns
  const columns = width >= 768 ? 5 : 3;
  const gap = spacing.md;
  const horizontalPadding = spacing.screenPadding * 2;
  const cardWidth = (width - horizontalPadding - gap * (columns - 1)) / columns;

  const displayBooks = maxRows ? books.slice(0, maxRows * columns) : books;

  // Build rows
  const rows: Array<Array<Book | DownloadedBook>> = [];
  for (let i = 0; i < displayBooks.length; i += columns) {
    rows.push(displayBooks.slice(i, i + columns));
  }

  return (
    <View style={styles.container}>
      {rows.map((row, rowIndex) => (
        <View key={rowIndex} style={[styles.row, { gap }]}>
          {row.map((book) => {
            const progress = 'last_read_page' in book ? progressMap[book.id] : undefined;
            return (
              <BookCard
                key={book.id}
                book={book}
                variant="small"
                progress={progress}
                onPress={undefined}
              />
            );
          })}
          {/* Fill empty cells in last row */}
          {row.length < columns &&
            Array.from({ length: columns - row.length }).map((_, i) => (
              <View key={`empty-${i}`} style={{ width: cardWidth }} />
            ))}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: spacing.screenPadding,
    gap: spacing.md,
  },
  row: {
    flexDirection: 'row',
  },
});
