import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import LoginPage from '../pages/LoginPage';
import { ThemeProvider } from '../context/ThemeContext';
import * as api from '../services/api';

vi.mock('../services/api', () => ({
  loginApi: vi.fn(),
}));

function renderLoginPage(onLoginSuccess = vi.fn()) {
  return render(
    <ThemeProvider>
      <LoginPage onLoginSuccess={onLoginSuccess} />
    </ThemeProvider>
  );
}

describe('LoginPage component', () => {
  const onLoginSuccess = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows error message when submitted with empty fields', () => {
    const { container } = renderLoginPage(onLoginSuccess);
    const form = container.querySelector('form')!;

    // Submit with empty inputs
    fireEvent.submit(form);

    const alert = screen.getByRole('alert');
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveTextContent(/Please enter your username and password/i);
    expect(api.loginApi).not.toHaveBeenCalled();
  });

  it('shows error message when submitted with missing username or password', () => {
    const { container } = renderLoginPage(onLoginSuccess);
    const form = container.querySelector('form')!;
    const usernameInput = screen.getByLabelText(/username/i);
    const passwordInput = screen.getByLabelText(/^password/i);

    // Enter username only
    fireEvent.change(usernameInput, { target: { value: 'admin' } });
    fireEvent.submit(form);
    expect(screen.getByRole('alert')).toHaveTextContent(/Please enter your password/i);

    // Clear username, enter password only
    fireEvent.change(usernameInput, { target: { value: '' } });
    fireEvent.change(passwordInput, { target: { value: 'secret' } });
    fireEvent.submit(form);
    expect(screen.getByRole('alert')).toHaveTextContent(/Please enter your username/i);
  });

  it('shows wrong credentials error when API returns 401 or unauthorized', async () => {
    vi.mocked(api.loginApi).mockRejectedValueOnce(new Error('401 Unauthorized: Incorrect password'));

    const { container } = renderLoginPage(onLoginSuccess);
    const form = container.querySelector('form')!;

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText(/^password/i), { target: { value: 'wrongpass' } });

    fireEvent.submit(form);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/Wrong username or password\. Please try again\./i);
    expect(onLoginSuccess).not.toHaveBeenCalled();
  });

  it('toggles password input type between password and text when show-password button is clicked', () => {
    renderLoginPage(onLoginSuccess);

    const passwordInput = screen.getByLabelText(/^password/i);
    expect(passwordInput).toHaveAttribute('type', 'password');

    const toggleBtn = screen.getByRole('button', { name: /show password/i });
    expect(toggleBtn).toBeInTheDocument();

    // Click to show password
    fireEvent.click(toggleBtn);
    expect(passwordInput).toHaveAttribute('type', 'text');
    expect(screen.getByRole('button', { name: /hide password/i })).toBeInTheDocument();

    // Click again to hide password
    fireEvent.click(screen.getByRole('button', { name: /hide password/i }));
    expect(passwordInput).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: /show password/i })).toBeInTheDocument();
  });
});
