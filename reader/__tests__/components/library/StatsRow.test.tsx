import React from 'react';
import { render } from '@testing-library/react-native';
import { StatsRow } from '../../../components/library/StatsRow';

describe('StatsRow', () => {
  it('renders all 4 stat cards with labels and values', () => {
    const { getByText } = render(
      <StatsRow pagesToday={47} wordsLearned={128} streak={12} timeRead="3h 24m" />
    );
    expect(getByText('TODAY')).toBeTruthy();
    expect(getByText('47')).toBeTruthy();
    expect(getByText(' pages')).toBeTruthy();
    expect(getByText('WORDS LEARNED')).toBeTruthy();
    expect(getByText('128')).toBeTruthy();
    expect(getByText('STREAK')).toBeTruthy();
    expect(getByText('12')).toBeTruthy();
    expect(getByText(' days')).toBeTruthy();
    expect(getByText('TIME READ')).toBeTruthy();
    expect(getByText('3h 24m')).toBeTruthy();
  });
});
