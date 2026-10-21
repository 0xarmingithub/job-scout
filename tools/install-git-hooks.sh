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

# In a git worktree `.git` is a file, not a directory. Ask git where the shared
# git directory really is, so the hook and the word list land in the right place.
if ! GIT_DIR_REAL="$(git -C "$REPO" rev-parse --git-common-dir 2>/dev/null)"; then
    echo "$REPO is not a git checkout." >&2
    exit 1
fi
case "$GIT_DIR_REAL" in
    /*|[A-Za-z]:*) ;;
    *) GIT_DIR_REAL="$REPO/$GIT_DIR_REAL" ;;
esac
HOOK="$GIT_DIR_REAL/hooks/pre-push"

mkdir -p "$GIT_DIR_REAL/hooks"

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

# The same ruff check CI runs, so a lint failure costs a minute here instead of
# a red build and a follow-up commit. Skipped when ruff is not installed: a
# contributor without it should still be able to push.
if "$python" -c "import ruff" >/dev/null 2>&1 || command -v ruff >/dev/null 2>&1; then
    echo "pre-push: linting ..."
    (cd "$repo" && "$python" -m ruff check job_scout tests tools)
else
    echo "pre-push: ruff is not installed, skipping the lint. CI still runs it."
fi

# A push with no version bump installs nowhere, because pip compares version
# strings and finds them equal. CI catches this too, but catching it here means
# fixing it in the commit rather than in a follow-up.
echo "pre-push: checking the version moved ..."
if [ -n "$remote_head" ]; then
    "$python" "$repo/tools/version_check.py" --against "$remote_head"
else
    "$python" "$repo/tools/version_check.py"
fi
HOOK_BODY

chmod +x "$HOOK"

echo "Installed $HOOK"
echo
echo "Next, if you have a private workspace: build your private word list with"
echo "  job-scout privacy init"
echo "It asks for your names, employers, town, server addresses and key filenames,"
echo "and saves them to"
echo "  $GIT_DIR_REAL/denylist.txt"
echo "That file lives inside .git, so git cannot commit it. You can also write the"
echo "terms there by hand, one per line."
echo
echo "Test it now with:"
echo "  python tools/pre_push_check.py"
