import { View, Text, Pressable, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Icon } from './Icon';
import { colors, typography, spacing } from '../../constants/theme';

interface HeaderProps {
  title: string;
  showBack?: boolean;
  backLabel?: string;
  subtitle?: string;
  rightContent?: React.ReactNode;
}

export function Header({ title, showBack, backLabel = 'Library', subtitle, rightContent }: HeaderProps) {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.container, { paddingTop: insets.top + spacing.sm }]}>
      <View style={styles.left}>
        {showBack ? (
          <Pressable onPress={() => router.back()} style={styles.backButton} hitSlop={8}>
            <Icon name="chevron-left" size={22} color={colors.textSecondary} />
            <Text style={styles.backText}>{backLabel}</Text>
          </Pressable>
        ) : (
          <Text style={styles.title}>{title}</Text>
        )}
      </View>
      {showBack && (
        <View style={styles.center}>
          <Text style={styles.centerTitle}>{title}</Text>
          {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
        </View>
      )}
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
  center: { flex: 2, alignItems: 'center' },
  right: { flex: 1, alignItems: 'flex-end', flexDirection: 'row', justifyContent: 'flex-end', gap: spacing.sm },
  title: {
    fontFamily: 'CormorantGaramond-SemiBold',
    fontSize: 24,
    color: colors.textPrimary,
    lineHeight: 30,
  },
  centerTitle: {
    fontFamily: 'DMSans-SemiBold',
    fontSize: 16,
    color: colors.textPrimary,
    lineHeight: 22,
  },
  subtitle: {
    fontFamily: 'DMSans',
    fontSize: 12,
    color: colors.textSecondary,
    lineHeight: 16,
  },
  backButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    paddingVertical: spacing.xs,
  },
  backText: {
    fontFamily: 'DMSans',
    fontSize: 15,
    color: colors.textSecondary,
  },
});
