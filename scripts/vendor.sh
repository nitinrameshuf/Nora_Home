#!/usr/bin/env bash
#
# Vendor the front-end libraries into static/nora_home/vendor/.
#
#     ./scripts/vendor.sh      (or: make vendor)
#
# They are committed to the repo on purpose. The house has to work with the
# internet down, the Pi should never run a build step, and a CDN outage must not
# blank the wall display. Two files, ~1.2MB total, and then it is nobody's problem
# again.
#
set -euo pipefail

ECHARTS_VERSION="${ECHARTS_VERSION:-5.5.1}"
GRIDSTACK_VERSION="${GRIDSTACK_VERSION:-10.3.1}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$ROOT/static/nora_home/vendor"
mkdir -p "$VENDOR"

fetch() {
    local url="$1" target="$2"
    if [[ -s "$target" ]]; then
        echo "  already have $(basename "$target")"
        return
    fi
    echo "  fetching $(basename "$target")"
    curl -fsSL --retry 3 "$url" -o "$target.tmp"
    # Only move into place once the download succeeded, so an interrupted run
    # never leaves a truncated library that fails silently in the browser.
    mv "$target.tmp" "$target"
}

echo "Vendoring front-end libraries into static/nora_home/vendor/"

fetch "https://cdn.jsdelivr.net/npm/echarts@${ECHARTS_VERSION}/dist/echarts.min.js" \
      "$VENDOR/echarts.min.js"

fetch "https://cdn.jsdelivr.net/npm/gridstack@${GRIDSTACK_VERSION}/dist/gridstack-all.js" \
      "$VENDOR/gridstack-all.js"

# gridstack-all.js ends in a `//# sourceMappingURL=gridstack-all.js.map` comment;
# without the map alongside it, Django's collectstatic post-processing treats that
# as a broken reference and fails the whole build.
fetch "https://cdn.jsdelivr.net/npm/gridstack@${GRIDSTACK_VERSION}/dist/gridstack-all.js.map" \
      "$VENDOR/gridstack-all.js.map"

fetch "https://cdn.jsdelivr.net/npm/gridstack@${GRIDSTACK_VERSION}/dist/gridstack.min.css" \
      "$VENDOR/gridstack.min.css"

cat > "$VENDOR/README.md" <<EOF
# Vendored libraries

Committed deliberately — see scripts/vendor.sh.

| File | Version | Licence |
|---|---|---|
| echarts.min.js | ${ECHARTS_VERSION} | Apache-2.0 |
| gridstack-all.js | ${GRIDSTACK_VERSION} | MIT |
| gridstack-all.js.map | ${GRIDSTACK_VERSION} | MIT |
| gridstack.min.css | ${GRIDSTACK_VERSION} | MIT |

Re-run \`make vendor\` after bumping a version in scripts/vendor.sh.
EOF

echo
echo "Done. Charts and drag-to-arrange are now available offline."
echo "Run 'python manage.py collectstatic' (or restart the containers) to publish them."
