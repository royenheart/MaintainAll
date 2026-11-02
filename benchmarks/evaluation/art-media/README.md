# Art-creation public media

Public images referenced by the legacy art-creation reports in
`docs/research/skill-benchmark-architecture-2026-10-09/outputs/*/report.json`.

These files are **LFS-tracked** by the repository's root `.gitattributes` (`*.png`,
`*.jpg`); the pointers are small. The content is copied or hard-linked into the generated
site by `benchmarks/evaluation/build_public_site.py`. GitHub Actions must check out with
`lfs: true` so the Pages artifact contains the actual images rather than LFS pointers.

The media is already present in the repository's LFS object store from earlier report
publication; this directory does not require a history rewrite and does not duplicate the
images in normal Git blobs.
