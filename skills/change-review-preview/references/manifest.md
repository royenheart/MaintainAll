# Review manifest

The helper uses Python 3.11+ and bundled browser assets. Resolve its script path relative to the skill directory. Put the manifest and review artifacts in the chosen output directory; source checkouts stay separate.

```json
{
  "project": "Example tools",
  "items": [{
    "id": "scope-reset",
    "title": "Reset scope and page together",
    "root": "scope-reset",
    "baseline": "baseline-revision",
    "candidate": "candidate-revision",
    "types": ["correctness", "request-scheduling"],
    "issue": {"title": "Changed scopes use the previous page size", "body": "issue.md"},
    "pr": {"title": "Apply scope and page atomically", "body": "pr.md", "draft": false},
    "patch": "change.patch",
    "files": [
      {"path": "data/samples.json", "sha256": "REPLACE_WITH_FILE_SHA256", "role": "data"},
      {"path": "scripts/reproduce.py", "sha256": "REPLACE_WITH_FILE_SHA256", "role": "source"}
    ],
    "metrics": [{"label": "Listing requests", "before": "2", "after": "1", "unit": "requests", "scope": "Three real callers, same native corpus", "source": "data/samples.json"}]
  }]
}
```

Replace illustrative hashes with actual file SHA-256 values. Drafts and patch are included automatically. Each additional servable/downloadable file requires a `files` entry and digest. Screenshots use `role: screenshot`; PNG/JPEG/GIF/WebP are supported. A file's optional `url` maps a published HTTP(S) reference to local verified bytes. Optional draft `url` fields show real remote links; the helper does not create/verify forge objects.

`id` is unique, using lowercase letters, digits and hyphens. `root` is relative to the manifest directory; body, patch, file and metric-source paths are relative to the item root. Absolute paths, parent traversal, duplicate archive names and paths resolving outside the root are rejected. Use deliberate public copies instead of exposing arbitrary checkout/home files.

`project`, `items`, item `id`, `title`, `root`, `issue`, `pr`, `patch` and `files` are required. `baseline`, `candidate`, `types` and `metrics` are optional. Each draft needs `title` and `body`; `pr.draft` is an explicit boolean. Metrics require `label`, `before`, `after`, `unit`, `scope` and an included `source`. Numeric values reach the UI as strings; raw datasets are served/archived byte-for-byte.

```sh
python3 scripts/review.py validate --manifest /path/to/review.json
python3 scripts/review.py serve --manifest /path/to/review.json --bind 127.0.0.1 --port 8787
python3 scripts/review.py pack --manifest /path/to/review.json --item scope-reset --output /path/to/scope-reset.zip
```

`validate` checks schema, path boundaries, hashes and metric references. Server startup verifies every listed file; requests re-read manifest/draft metadata and verify selected evidence bytes before serving them. This avoids hashing unrelated large captures for every image request. Intentionally update evidence hashes after an edit and refresh. HTTP errors omit exception details that can expose local paths or manifest values; run `validate` locally for diagnostics. Large or binary evidence is offered as a complete download instead of automatic text rendering. `pack` produces an ordinary ZIP and `review-manifest.json` with computed sizes/digests, refusing to overwrite existing output. Archive serving uses one temporary ZIP at a time.

The helper has no publication action or consent flag. Current user instructions govern publication and ready/draft state. A requested LAN binding leaves the allowlist unchanged.
