import React from 'react';
import { render } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
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

const metrics = {
  insets: { top: 0, bottom: 0, left: 0, right: 0 },
  frame: { x: 0, y: 0, width: 390, height: 844 },
};

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <SafeAreaProvider initialMetrics={metrics}>{ui}</SafeAreaProvider>
  );
}

describe('Header', () => {
  it('renders serif title when not showing back', () => {
    const { getByText } = renderWithProviders(<Header title="Library" />);
    expect(getByText('Library')).toBeTruthy();
  });

  it('renders back button with chevron icon when showBack is true', () => {
    const { getByTestId, getByText } = renderWithProviders(<Header title="Settings" showBack />);
    expect(getByTestId('icon-chevron-left')).toBeTruthy();
    expect(getByText('Library')).toBeTruthy(); // default backLabel
  });

  it('uses custom backLabel', () => {
    const { getByText } = renderWithProviders(<Header title="Settings" showBack backLabel="Profile" />);
    expect(getByText('Profile')).toBeTruthy();
  });

  it('renders subtitle when provided', () => {
    const { getByText } = renderWithProviders(<Header title="Reading" showBack subtitle="Chapter 1" />);
    expect(getByText('Chapter 1')).toBeTruthy();
  });

  it('renders right content', () => {
    const { Text } = require('react-native');
    const { getByText } = renderWithProviders(
      <Header title="Library" rightContent={<Text>Right</Text>} />
    );
    expect(getByText('Right')).toBeTruthy();
  });
});
