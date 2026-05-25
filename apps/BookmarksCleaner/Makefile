# BookmarksCleaner build system
# Usage:
#   make           Build to build/ directory + create zip
#   make build     Same as above
#   make check     Syntax-check all files
#   make clean     Remove build artifacts
#   make dist      Create distributable zip only
#   make version   Show current version from VERSION file
#
# Version: edit VERSION file (single source of truth), injected into manifest.json at build time.

EXT_NAME   := BookmarksCleaner
BUILD_DIR  := build
DIST_DIR   := $(BUILD_DIR)/$(EXT_NAME)
VERSION    := $(shell cat VERSION 2>/dev/null || echo '0.0.0')
ZIP_FILE   := $(BUILD_DIR)/bookmarks-cleaner-$(VERSION).zip

# Self-hosted update URL (set to your updates.xml URL if self-hosting .crx)
# Leave empty for dev-mode (update check uses GitHub fetch instead)
UPDATE_URL ?=

SRC_FILES  := manifest.json background.js sidepanel.html sidepanel.js \
              settings.html settings.js icons/icon128.png \
              lib/deepseek.js lib/title_cleaner.js lib/knowledge_base.js \
              lib/webdav.js lib/markdown_renderer.js lib/prompts.js \
              lib/bookmark_organizer.js

.PHONY: all build check clean dist version test test-coverage

all: build

build: check $(ZIP_FILE)
	@echo "✅ Build complete: $(ZIP_FILE) (v$(VERSION))"
	@ls -lh $(ZIP_FILE)

$(ZIP_FILE): $(SRC_FILES) VERSION
	@echo "📦 Packaging v$(VERSION)..."
	@rm -rf $(DIST_DIR) $(BUILD_DIR)/bookmarks-cleaner-*.zip
	@mkdir -p $(DIST_DIR)/icons $(DIST_DIR)/lib
	@# Inject version into manifest; strip update_url line if empty
	@sed -e 's/\$$VERSION\$$/$(VERSION)/g' \
	     -e 's|\$$UPDATE_URL\$$|$(UPDATE_URL)|g' \
	     manifest.json > $(DIST_DIR)/manifest.json.tmp
	@if [ -z "$(UPDATE_URL)" ]; then \
		sed -i '/"update_url"/d' $(DIST_DIR)/manifest.json.tmp; \
	fi
	@mv $(DIST_DIR)/manifest.json.tmp $(DIST_DIR)/manifest.json
	@cp background.js $(DIST_DIR)/
	@cp sidepanel.html sidepanel.js $(DIST_DIR)/
	@cp settings.html settings.js $(DIST_DIR)/
	@cp icons/icon128.png $(DIST_DIR)/icons/
	@cp lib/*.js $(DIST_DIR)/lib/
	@# Generate updates.xml for self-hosted auto-update
	@$(MAKE) updates
	@# Zip with manifest at root (Chrome requires this)
	@cd $(DIST_DIR) && zip -qr ../$(notdir $(ZIP_FILE)) .
	@echo "   → $(ZIP_FILE)"

check:
	@echo "🔍 Checking VERSION file..."
	@test -f VERSION || { echo "   MISSING: VERSION file"; exit 1; }
	@echo "   version: $(VERSION)"
	@echo "🔍 Checking manifest.json (source)..."
	@python3 -c "import json; m=json.load(open('manifest.json')); \
		assert m.get('manifest_version')==3, 'Must be MV3'; \
		assert 'bookmarks' in m.get('permissions',[]), 'Missing bookmarks permission'; \
		print('   manifest.json: valid MV3')"
	@echo "🔍 Checking JS syntax..."
	@for f in $(filter %.js,$(SRC_FILES)); do \
		node -c $$f 2>&1 || exit 1; \
	done
	@echo "   All JS: syntax OK"
	@echo "🔍 Checking required files..."
	@for f in $(SRC_FILES) VERSION; do \
		test -f $$f || { echo "   MISSING: $$f"; exit 1; }; \
	done
	@echo "   All files present ($(words $(SRC_FILES)) src files + VERSION)"
	@echo "✅ All checks passed"

# Generate updates.xml for Chrome self-hosted auto-update.
# Requires EXTENSION_ID to be set (the extension's 32-char public key hash).
# Usage: make updates EXTENSION_ID=abcdef...
updates:
	@if [ -n "$(EXTENSION_ID)" ] && [ -n "$(UPDATE_URL)" ]; then \
		mkdir -p $(BUILD_DIR); \
		echo '<?xml version="1.0" encoding="UTF-8"?>' > $(BUILD_DIR)/updates.xml; \
		echo '<gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">' >> $(BUILD_DIR)/updates.xml; \
		echo '  <app appid="$(EXTENSION_ID)">' >> $(BUILD_DIR)/updates.xml; \
		echo '    <updatecheck codebase="$(UPDATE_URL)/bookmarks-cleaner-$(VERSION).crx" version="$(VERSION)" />' >> $(BUILD_DIR)/updates.xml; \
		echo '  </app>' >> $(BUILD_DIR)/updates.xml; \
		echo '</gupdate>' >> $(BUILD_DIR)/updates.xml; \
		echo "   → build/updates.xml"; \
	else \
		echo "   (skipped: set EXTENSION_ID and UPDATE_URL for self-hosted updates)"; \
	fi

dist: $(ZIP_FILE)
	@echo "✅ Distributable: $(ZIP_FILE)"

clean:
	@rm -rf $(BUILD_DIR)
	@echo "🧹 Cleaned build directory"

version:
	@echo "BookmarksCleaner v$(VERSION)"

test:
	@echo "🧪 Running unit tests..."
	@node --experimental-vm-modules node_modules/.bin/jest tests/unit/ --no-coverage

test-coverage:
	@echo "🧪 Running unit tests with coverage..."
	@node --experimental-vm-modules node_modules/.bin/jest tests/unit/ --coverage
