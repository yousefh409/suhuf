import { View, Text, Pressable, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { colors, typography, spacing } from '../../constants/theme';

interface HeaderProps {
  title: string;
  showBack?: boolean;
  rightContent?: React.ReactNode;
}

export function Header({ title, showBack, rightContent }: HeaderProps) {
  const router = useRouter();
  return (
    <View style={styles.container}>
      <View style={styles.left}>
        {showBack && (
          <Pressable onPress={() => router.back()} style={styles.backButton}>
            <Text style={styles.backText}>{'‹ Library'}</Text>
          </Pressable>
        )}
        {!showBack && <Text style={styles.title}>{title}</Text>}
      </View>
      {showBack && <Text style={styles.centerTitle}>{title}</Text>}
      <View style={styles.right}>{rightContent}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.screenPadding,
    paddingVertical: spacing.md,
    backgroundColor: colors.background,
  },
  left: { flex: 1, alignItems: 'flex-start' },
  right: { flex: 1, alignItems: 'flex-end', flexDirection: 'row', justifyContent: 'flex-end', gap: spacing.sm },
  title: { fontFamily: 'DMSans-Bold', ...typography.h1, color: colors.textPrimary },
  centerTitle: { fontFamily: 'DMSans-SemiBold', ...typography.h3, color: colors.textPrimary },
  backButton: { paddingVertical: spacing.xs },
  backText: { fontFamily: 'DMSans', fontSize: 16, color: colors.textSecondary },
});
