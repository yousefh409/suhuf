import { View, StyleSheet } from 'react-native';
import { colors, borderRadius } from '../../constants/theme';

interface ProgressBarProps {
  progress: number; // 0-1
  color?: string;
  height?: number;
}

export function ProgressBar({ progress, color = colors.accent, height = 4 }: ProgressBarProps) {
  return (
    <View style={[styles.track, { height }]}>
      <View
        style={[
          styles.fill,
          { width: `${Math.min(progress * 100, 100)}%`, backgroundColor: color, height },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  track: { flex: 1, backgroundColor: '#E8E0D8', borderRadius: borderRadius.full, overflow: 'hidden' },
  fill: { borderRadius: borderRadius.full },
});
