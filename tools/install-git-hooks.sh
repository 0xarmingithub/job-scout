#!/usr/bin/env bash
# install-git-hooks.sh: make `git push` refuse to publish anything private.
#
#   bash tools/install-git-hooks.sh
#
# Installs a pre-push hook that runs tools/pre_push_check.py against the commits
# you are about to push. A failure stops the push.
#
# Undo it with:
#   rm .git/hooks/pre-push

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$REPO/.git/hooks/pre-push"

if [ ! -d "$REPO/.git" ]; then
    echo "$REPO is not a git checkout." >&2
    exit 1
fi

mkdir -p "$REPO/.git/hooks"

cat > "$HOOK" <<'HOOK_BODY'
#!/usr/bin/env bash
# Installed by tools/install-git-hooks.sh. Safe to delete.
set -euo pipefail

python="$(command -v python3 || command -v python || true)"
if [ -z "$python" ]; then
    echo "pre-push: no python found, skipping the private-content check." >&2
    exit 0
fi

repo="$(git rev-parse --show-toplevel)"
remote_head="$(git rev-parse --verify --quiet '@{upstream}' || true)"

if [ -n "$remote_head" ]; then
    range="$remote_head..HEAD"
else
    range=""
fi

echo "pre-push: checking for private content ..."
if [ -n "$range" ]; then
    "$python" "$repo/tools/pre_push_check.py" --require-denylist --range "$range"
else
    "$python" "$repo/tools/pre_push_check.py" --require-denylist
fi
HOOK_BODY

chmod +x "$HOOK"

echo "Installed $HOOK"
echo
echo "Next, if you have a private workspace: put your own names, employers,"
echo "town, server addresses and key filenames in"
echo "  $REPO/.git/denylist.txt"
echo "one per line. That file lives inside .git, so git cannot commit it."
echo
echo "Test it now with:"
echo "  python tools/pre_push_check.py"
