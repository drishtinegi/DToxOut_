import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api, authStorage } from '../services/api';

vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api')>();
  return {
    ...actual,
  };
});

describe('Phase 6 Frontend Operations & Logout', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('stores and removes auth token correctly on session management', () => {
    authStorage.setToken('sample-jwt-token');
    authStorage.setUser({ id: 'u1', email: 'test@example.com', username: 'testuser', role: 'USER' });

    expect(authStorage.getToken()).toBe('sample-jwt-token');
    expect(authStorage.getUser()?.email).toBe('test@example.com');

    authStorage.removeToken();

    expect(authStorage.getToken()).toBeNull();
    expect(authStorage.getUser()).toBeNull();
  });

  it('invokes logout API and clears client storage', async () => {
    authStorage.setToken('test-token');
    authStorage.setUser({ id: 'u2', email: 'logout@example.com', username: 'user2', role: 'USER' });

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ message: 'Logged out successfully.' }),
      })
    );

    const res = await api.logout();
    expect(res.message).toBe('Logged out successfully.');
    expect(authStorage.getToken()).toBeNull();
  });
});
