---
name: daed-connectivity
description: When to use — daed/gost connectivity probes and Telegram CIDR/routing checks against deploy/daed configs.
---

# Daed connectivity

## Context

Topology under `deploy/daed`:

1. Local clients talk to **gost** sidecar: SOCKS5 `:20170`, HTTP `:20171`.
2. gost traffic is redirected into **daed** tproxy (`tproxy_port: 12345`).
3. daed routes by `deploy/daed/config/routing.conf` to sticky outbound groups defined in `deploy/daed/config/groups.txt` (e.g. `proxy`, `telegram`, `openai`), then to subscription nodes in wing.db / Web UI.

Key files (read-only unless a mission explicitly allows writes):

- `deploy/daed/config/routing.conf` — domain/dip rules → outbound groups
- `deploy/daed/config/groups.txt` — sticky group names and policies
- Official Telegram CIDRs: `https://core.telegram.org/resources/cidr.txt`

## Instructions

1. Read `routing.conf` and `groups.txt`. List sticky outbound groups and which domains/IPs map to them.
2. For each sticky group / proxy target that needs a live check, probe via the current gost proxy, e.g.:

   ```bash
   curl -x socks5://127.0.0.1:20170 -I -m 10 https://example.com
   ```

   HTTP proxy alternative: `curl -x http://127.0.0.1:20171 -I -m 10 https://…`.
3. On failure, record in the report draft:
   - **proxy/group** — outbound group or node under test
   - **target** — URL or host probed
   - **error** — curl exit / HTTP status / timeout
   - **suggestion** — e.g. check group membership in Web UI, subscription health, or routing rule
4. Fetch official Telegram CIDRs and diff against `dip(...)` lines that route to `telegram` in `routing.conf`:

   ```bash
   curl -sS -m 30 https://core.telegram.org/resources/cidr.txt
   ```

   Output add/remove suggestions for missing or stale CIDRs (do not auto-edit configs unless the mission allows).
5. Merge connectivity and CIDR results into a standard report with `## connectivity` and `## cidr-diff` sections.

## Constraints

- Do **not** modify `wing.db` (or other daed runtime DB) unless the active mission explicitly allows it.
- Run only commands matching the mission `allowed_commands` whitelist (curl via gost / official CIDR fetch / `cat` of the two config files).
- Prefer SOCKS5 `:20170` for probes; use HTTP `:20171` only when needed for comparison.
- Keep suggestions actionable; do not invent node credentials or rewrite subscription URLs.

## Examples

**Probe Telegram via gost:**

```bash
curl -x socks5://127.0.0.1:20170 -I -m 10 https://api.telegram.org
```

**Read sticky groups:**

```bash
cat deploy/daed/config/groups.txt
```

**Unreachable report row (draft):**

| proxy/group | target | error | suggestion |
|-------------|--------|-------|------------|
| telegram | https://api.telegram.org | curl exit 28 (timeout) | Confirm telegram group has a live node in daed UI; check subscription ALIVE |
