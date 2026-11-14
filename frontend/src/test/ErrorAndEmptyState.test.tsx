import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ErrorState from '../components/ui/ErrorState';
import EmptyState from '../components/ui/EmptyState';

describe('ErrorState component', () => {
  it('renders custom error title and message', () => {
    render(
      <ErrorState
        title="Server unreachable"
        message="Please check your network connection and try again."
      />
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Server unreachable')).toBeInTheDocument();
    expect(
      screen.getByText('Please check your network connection and try again.')
    ).toBeInTheDocument();
  });

  it('calls onRetry callback when the Retry button is clicked', () => {
    const handleRetry = vi.fn();

    render(
      <ErrorState
        title="Connection lost"
        message="Cannot reach the server."
        onRetry={handleRetry}
      />
    );

    const retryBtn = screen.getByRole('button', { name: /try again/i });
    expect(retryBtn).toBeInTheDocument();

    fireEvent.click(retryBtn);
    expect(handleRetry).toHaveBeenCalledTimes(1);
  });

  it('disables the retry button and shows retrying label when isRetrying is true', () => {
    const handleRetry = vi.fn();

    render(
      <ErrorState
        title="Connecting…"
        message="Attempting to re-establish link."
        onRetry={handleRetry}
        isRetrying={true}
      />
    );

    const retryBtn = screen.getByRole('button');
    expect(retryBtn).toBeDisabled();
    expect(screen.getByText('Retrying…')).toBeInTheDocument();
  });
});

describe('EmptyState component', () => {
  it('renders default title and description', () => {
    render(<EmptyState />);

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText('No traffic activity yet')).toBeInTheDocument();
    expect(
      screen.getByText(
        'As vehicles move through the network, data will appear here automatically.'
      )
    ).toBeInTheDocument();
  });

  it('renders custom title, description, and action button that works', () => {
    const handleAction = vi.fn();

    render(
      <EmptyState
        title="No warnings recorded"
        description="Traffic has stayed below the congestion limits."
        action={
          <button type="button" onClick={handleAction}>
            Refresh list
          </button>
        }
      />
    );

    expect(screen.getByText('No warnings recorded')).toBeInTheDocument();
    expect(
      screen.getByText('Traffic has stayed below the congestion limits.')
    ).toBeInTheDocument();

    const actionBtn = screen.getByRole('button', { name: 'Refresh list' });
    fireEvent.click(actionBtn);
    expect(handleAction).toHaveBeenCalledTimes(1);
  });
});
