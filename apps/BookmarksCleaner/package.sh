#!/bin/bash
# Package BookmarksCleaner for Chrome Web Store submission
# Usage: bash package.sh

set -e
cd "$(dirname "$0")"

EXT_DIR="BookmarksCleaner"
ZIP_FILE="bookmarks-cleaner-v1.1.zip"

# Remove dev junk
find "$EXT_DIR" -name ".DS_Store" -delete 2>/dev/null || true

# Create zip (exclude hidden/files not needed for production)
zip -r "$ZIP_FILE" "$EXT_DIR" \
  -x "*.md" "*.sh" "*.git*"

echo "✅ Packaged: $ZIP_FILE"
ls -lh "$ZIP_FILE"
