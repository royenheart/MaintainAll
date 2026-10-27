/**
 * Minimal host HTTP client for the browser half. Both helpers bound the wait
 * so a stuck save/edit cannot keep the modal closed forever.
 */

/** Base pathname of the host routes this client talks to. */
export const ROUTE_BASE = '/plugins/@royenheart/dsh-plugin-maintainall'

export async function postJson(path: string, body: unknown): Promise<boolean> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 30_000)
  try {
    const response = await fetch(path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    return response.ok
  } catch {
    return false
  } finally {
    clearTimeout(timer)
  }
}

/** POST a Save/Edit request, returning the host's error text when it fails. */
export async function postJsonError(path: string, body: unknown, fallback: string): Promise<string | null> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 30_000)
  try {
    const response = await fetch(path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    if (response.ok) return null
    const payload = await response.json().catch(() => null) as { error?: unknown } | null
    return typeof payload?.error === 'string' && payload.error !== ''
      ? payload.error
      : fallback
  } catch {
    return fallback
  } finally {
    clearTimeout(timer)
  }
}


/** POST a Save/Edit request and keep a created session id for navigation. */
export async function postJsonEdit(
  path: string,
  body: unknown,
  fallback: string,
): Promise<{ error: string | null; sessionId?: string }> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 30_000)
  try {
    const response = await fetch(path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    const payload = await response.json().catch(() => null) as {
      error?: unknown
      sessionId?: unknown
    } | null
    if (!response.ok) {
      return {
        error: typeof payload?.error === 'string' && payload.error !== '' ? payload.error : fallback,
      }
    }
    return {
      error: null,
      ...(typeof payload?.sessionId === 'string' ? { sessionId: payload.sessionId } : {}),
    }
  } catch {
    return { error: fallback }
  } finally {
    clearTimeout(timer)
  }
}
