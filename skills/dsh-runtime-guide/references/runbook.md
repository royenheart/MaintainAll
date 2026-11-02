# Runtime runbook

## Client change

```sh
# build the client
npm run build
# refresh/HMR only if `pnpm run dev:web` is running; otherwise rebuild and hard-refresh.
# If registration/composition changed, restart the host.
```

Verify the served client and one rendered surface. Do not claim HMR for a host row.

## Host plugin change

```sh
# bounded build/test
npm run build && npm test
# stop the host, then start the same profile under its supervisor
```

After boot, check for pending services, plugin-tree failure, and the expected roster
entry; then exercise one message/tool/response path.

## dsh version change

Do not run the global install from this session. Hand off:

```sh
# external terminal, after stopping the processes that own this install/profile
npm install -g @deepseek-ai/dsh@<exact-version>
dsh --version
dsh web
```

If the install was interrupted, re-run the same pinned install; do not copy package
directories or write shims by hand.
