import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import LiveStatusBadge from '../components/ui/LiveStatusBadge';
import * as TrafficContext from '../context/TrafficContext';

describe('LiveStatusBadge component', () => {
  it('renders Live state when connectionStatus is connected', () => {
    vi.spyOn(TrafficContext, 'useTraffic').mockReturnValue({
      connectionStatus: 'connected',
      lastUpdate: 1700000000000,
    } as any);

    render(<LiveStatusBadge />);

    const badge = screen.getByRole('status');
    expect(badge).toBeInTheDocument();
    expect(screen.getByText('Live')).toBeInTheDocument();
    expect(badge).toHaveClass('text-ok');
    expect(screen.getByText(/last updated/i)).toBeInTheDocument();
  });

  it('renders Offline state when connectionStatus is disconnected', () => {
    vi.spyOn(TrafficContext, 'useTraffic').mockReturnValue({
      connectionStatus: 'disconnected',
      lastUpdate: null,
    } as any);

    render(<LiveStatusBadge />);

    const badge = screen.getByRole('status');
    expect(badge).toBeInTheDocument();
    expect(screen.getByText('Offline')).toBeInTheDocument();
    expect(badge).toHaveClass('text-bad');
  });

  it('renders Offline state when connectionStatus is error', () => {
    vi.spyOn(TrafficContext, 'useTraffic').mockReturnValue({
      connectionStatus: 'error',
      lastUpdate: null,
    } as any);

    render(<LiveStatusBadge />);

    const badge = screen.getByRole('status');
    expect(badge).toBeInTheDocument();
    expect(screen.getByText('Offline')).toBeInTheDocument();
    expect(badge).toHaveClass('text-bad');
  });

  it('hides timestamp when showTimestamp is false', () => {
    vi.spyOn(TrafficContext, 'useTraffic').mockReturnValue({
      connectionStatus: 'connected',
      lastUpdate: 1700000000000,
    } as any);

    render(<LiveStatusBadge showTimestamp={false} />);

    expect(screen.getByText('Live')).toBeInTheDocument();
    expect(screen.queryByText(/last updated/i)).not.toBeInTheDocument();
  });
});
