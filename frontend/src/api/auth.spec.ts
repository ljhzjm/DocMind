import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAuthSession, loginWithApiKey, logout } from './auth'

describe('auth api', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('logs in with an API key and relies on the session cookie', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ authenticated: true, auth_required: true }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    )

    const session = await loginWithApiKey('secret-key')

    expect(session.authenticated).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/session',
      expect.objectContaining({
        method: 'POST',
        credentials: 'same-origin',
      }),
    )
  })

  it('returns an unauthenticated session for HTTP 401', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
    )

    await expect(fetchAuthSession()).resolves.toEqual({
      authenticated: false,
      auth_required: true,
    })
  })

  it('clears the server-side session on logout', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await logout()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/session',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })
})
