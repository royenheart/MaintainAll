/**
 * Webhook trigger helpers: bearer-token verification and body parsing.
 *
 * Pure functions over header maps and raw bodies; the host owns the HTTP
 * listener. Nothing here performs IO.
 */

/**
 * Verify `Authorization: Bearer <expected>` against a headers map.
 *
 * Header lookup is case-insensitive and tolerates multi-value headers; the
 * `Bearer` scheme is matched case-insensitively per RFC 7235. An empty
 * `expected` token never verifies.
 */
export function verifyWebhookToken(
  headers: Record<string, string | string[] | undefined>,
  expected: string,
): boolean {
  if (expected === '') {
    return false
  }
  const values: string[] = []
  for (const [name, value] of Object.entries(headers)) {
    if (name.toLowerCase() !== 'authorization' || value === undefined) {
      continue
    }
    if (Array.isArray(value)) values.push(...value)
    else values.push(value)
  }
  return values.some((value) => {
    const match = /^Bearer\s+(.+)$/i.exec(value.trim())
    if (!match) return false
    return match[1]!.trim() === expected
  })
}

/** Parse a webhook request body as JSON. Returns null when malformed. */
export function parseWebhookBody(body: string): unknown {
  try {
    return JSON.parse(body)
  } catch {
    return null
  }
}
