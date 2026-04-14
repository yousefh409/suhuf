import React from 'react';
import { render } from '@testing-library/react-native';
import { Header } from '../../../components/ui/Header';

// Mock expo-router
jest.mock('expo-router', () => ({
  useRouter: () => ({ back: jest.fn() }),
}));

// Mock Icon component
jest.mock('../../../components/ui/Icon', () => {
  const { Text } = require('react-native');
  return {
    Icon: (props: any) => <Text testID={`icon-${props.name}`}>{props.name}</Text>,
  };
});

describe('Header', () => {
  it('renders serif title when not showing back', () => {
    const { getByText } = render(<Header title="Library" />);
    expect(getByText('Library')).toBeTruthy();
  });

  it('renders back button with chevron icon when showBack is true', () => {
    const { getByTestId, getByText } = render(<Header title="Settings" showBack />);
    expect(getByTestId('icon-chevron-left')).toBeTruthy();
    expect(getByText('Library')).toBeTruthy(); // default backLabel
  });

  it('uses custom backLabel', () => {
    const { getByText } = render(<Header title="Settings" showBack backLabel="Profile" />);
    expect(getByText('Profile')).toBeTruthy();
  });

  it('renders subtitle when provided', () => {
    const { getByText } = render(<Header title="Reading" showBack subtitle="Chapter 1" />);
    expect(getByText('Chapter 1')).toBeTruthy();
  });

  it('renders right content', () => {
    const { Text } = require('react-native');
    const { getByText } = render(
      <Header title="Library" rightContent={<Text>Right</Text>} />
    );
    expect(getByText('Right')).toBeTruthy();
  });
});
