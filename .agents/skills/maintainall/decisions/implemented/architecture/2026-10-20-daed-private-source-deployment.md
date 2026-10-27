# Decision: Private-source daed image preparation

Status: implemented — deployment selects an explicit runtime image and supports an opt-in local-source build without activating it

## Problem

The upstream GHCR latest image remains daed 1.27.0 while newer source releases and dependency fixes exist. The privately imported daed checkout still records an older wing revision, so changing image ownership alone does not deliver all fixes. The currently running proxy must remain active until the operator explicitly approves a cutover.

## Decision

[The runtime Compose file](../../../../../../deploy/daed/docker-compose.yml) accepts `DAED_IMAGE` and defaults to the exact existing production image digest. [The build overlay](../../../../../../deploy/daed/docker-compose.build.yml) is explicitly named, requires an independent candidate tag, local source directory, and source revision, and uses the fork's Dockerfile. It is not auto-discovered as an override. [The env example](../../../../../../deploy/daed/.env.example) contains no credentials. Runtime data mounts and service settings stay unchanged.

[The deployment README](../../../../../../deploy/daed/README.md#maintaining-the-private-fork) owns source/dependency prerequisites, local build and private GHCR options, and the distinction between preparation and an approved service replacement. It requires SQLite-consistent backups and migration-aware rollback. Source labels identify the supplied clean checkout; they do not attest that its dependencies are fixed or that the image passed tests. No private-fork CI or source changes are included in this deployment change.

## Alternatives considered

- **Switch directly to a private `latest` tag.** No such publication has been verified, and a mutable tag obscures the reviewed build. Explicit tags or registry digests keep selection deliberate.
- **Add build to the runtime service or use an auto-loaded override.** Routine Compose commands could unexpectedly select or build a candidate. The separate overlay keeps image preparation opt-in.
- **Build from an authenticated remote Git context.** The private source already exists locally. Local context avoids passing top-level Git credentials to Docker; nested dependencies still require initialization in the checkout.
- **Create an update daemon or restart helper.** The operator requires explicit approval for activation. Documented manual cutover keeps preparation free of service mutations.

## Consequences

Configuration rendering and candidate builds do not activate a new service. Builds still consume resources, so separate-host or CI builds are preferred when production headroom is limited. Updating wing/core/outbound and maintaining the private publishing workflow remain source-repository responsibilities. Production stays on the pinned old image until a reviewed candidate is explicitly selected and activated; the digest pin is a compatibility hold, not a claim that the old image is fixed.
