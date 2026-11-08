#!/usr/bin/env bash
set -euo pipefail
bundle_dir="$(cd -- "$(dirname -- "$0")" && pwd -P)"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Self-Sourcing Pudding needs Python 3.11 or newer.")'
mkdir -p "$bundle_dir/.pudding/bin"
cat > "$bundle_dir/.pudding/bin/pudding" <<'PUDDING'
#!/usr/bin/env bash
set -euo pipefail
bundle_dir="$(cd -- "$(dirname -- "$0")/../.." && pwd -P)"
exec python3 "$bundle_dir/rig.py" "$@"
PUDDING
chmod +x "$bundle_dir/.pudding/bin/pudding"
if [[ "${1:-}" == "--install-only" ]]; then
    printf 'Installed: %s\n' "$bundle_dir/.pudding/bin/pudding"
    exit 0
fi
cd "$bundle_dir"
exec .pudding/bin/pudding walk "$@"
