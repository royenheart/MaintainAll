# Agent Note: Hysteria2 uses BBR instead of a declared rate

Status: implemented — deploy/proxy pins Hysteria2 to BBR3 and ignores client-declared bandwidth.

## Problem

A Hysteria2 link with no upload/download rate still enables Brutal when the client has both global bandwidth values set. Brutal sends at that fixed rate and does not slow down on loss, so a rate above the path bottleneck fills router buffers.

## Decision

- Rendered `hysteria2://` links always include `cc_override=bbr3`.
- The sing-box inbound sets `ignore_client_bandwidth: true`, so the server sends with BBR instead of the rate the client announces.
- The templates do not emit `up`/`down` or `upmbps`/`downmbps`. Those fields are a client declaration of path bandwidth and turn on Brutal.
- `rotate.sh` keeps `cc_override=bbr3` on regenerated links and sets `ignore_client_bandwidth` when it rewrites the server config.

An already imported client link does not change until `cc_override=bbr3` is added to its query string.

## Alternatives considered

- Put a fixed upload/download number in the deploy script. Rejected: the server does not know each client's path, and a number that is too high is what enables the buffer flood.
- Only change the server flag. Rejected: the client can still send with Brutal on the upload direction when its global bandwidth pair is set.

## Consequences

New imports and rotations use BBR without a home-line rate. Other Hysteria2 nodes that are not produced by this script keep their previous behavior.
