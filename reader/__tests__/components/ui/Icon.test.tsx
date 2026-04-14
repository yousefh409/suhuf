import React from 'react';
import { render } from '@testing-library/react-native';
import { Icon } from '../../../components/ui/Icon';

// Mock @expo/vector-icons
jest.mock('@expo/vector-icons', () => {
  const { Text } = require('react-native');
  return {
    Feather: (props: any) => <Text testID="feather-icon" {...props} />,
  };
});

describe('Icon', () => {
  it('renders with default props', () => {
    const { getByTestId } = render(<Icon name="search" />);
    const icon = getByTestId('feather-icon');
    expect(icon).toBeTruthy();
    expect(icon.props.name).toBe('search');
    expect(icon.props.size).toBe(20);
  });

  it('accepts custom size', () => {
    const { getByTestId } = render(<Icon name="search" size={24} />);
    expect(getByTestId('feather-icon').props.size).toBe(24);
  });

  it('accepts custom color', () => {
    const { getByTestId } = render(<Icon name="search" color="#FF0000" />);
    expect(getByTestId('feather-icon').props.color).toBe('#FF0000');
  });

  it('uses textPrimary as default color', () => {
    const { getByTestId } = render(<Icon name="search" />);
    // textPrimary from theme is #1A1208
    expect(getByTestId('feather-icon').props.color).toBe('#1A1208');
  });
});
