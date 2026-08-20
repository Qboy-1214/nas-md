#!/usr/bin/env bash
# Hash-version top-level static assets in web/lib/ for long-term cache invalidation.
# Does NOT touch vditor-cdn internal files (Vditor hardcodes those paths at runtime).
set -euo pipefail

WEB_ROOT="${1:-web}"

# Only hash .js and .css files directly referenced from index.html (top-level only).
# Skip vditor-cdn/** and other nested packages with hardcoded internal paths.
find "$WEB_ROOT/lib" -type f \( -name "*.js" -o -name "*.css" \) \
  ! -path "*/vditor-cdn/*" \
  ! -path "*/katex/*" \
  ! -path "*/highlight.js/*" \
  | sort \
  | while IFS= read -r f; do
      hash=$(sha1sum "$f" | cut -c1-8)
      base=$(basename "$f")
      ext="${base##*.}"
      name="${base%.*}"
      newname="${name}.${hash}.${ext}"
      mv "$f" "$(dirname "$f")/$newname"
      # Update index.html reference (only exact basename matches)
      if [[ -f "$WEB_ROOT/index.html" ]]; then
        sed -i "s|\"${base}\"|\"${newname}\"|g" "$WEB_ROOT/index.html"
        sed -i "s|'${base}'|'${newname}'|g" "$WEB_ROOT/index.html"
      fi
      echo "  hashed: $base → $newname"
    done

echo "Hash versioning complete."
