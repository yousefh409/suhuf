import { Feather } from '@expo/vector-icons';
import { colors } from '../../constants/theme';

export type IconName = React.ComponentProps<typeof Feather>['name'];

interface IconProps {
  name: IconName;
  size?: number;
  color?: string;
}

export function Icon({ name, size = 20, color = colors.textPrimary }: IconProps) {
  return <Feather name={name} size={size} color={color} />;
}
