#!/usr/bin/env bash
set -euo pipefail
cd ~/polebarn_control

# Ensure SSH remote
git remote set-url origin git@github.com:ntsteele/polebarn_control.git

# Trust GitHub host (no interactive prompt)
mkdir -p ~/.ssh
ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null || true

# Pick an existing private key (override with: KEY=/path/to/key ./.push_now.sh)
choose_key() {
  for k in "$HOME/.ssh/polebarn_control" "$HOME/.ssh/id_ed25519" "$HOME/.ssh/id_rsa"; do
    [ -f "$k" ] && { echo "$k"; return; }
  done
  # Fallback: first private key in ~/.ssh
  for k in "$HOME"/.ssh/*; do
    [[ -f "$k" && "$k" != *.pub ]] && { echo "$k"; return; }
  done
  echo ""
}
KEY="${KEY:-$(choose_key)}"
[ -n "$KEY" ] || { echo "No SSH private key found under ~/.ssh"; exit 1; }
echo "Using key: $KEY"

# Stage & commit whatever’s pending (safe if nothing changed)
git add -A
git commit -m "update" || true

# Fast-forward to remote if needed (no rebase prompts)
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git fetch origin
git merge --ff-only "origin/$BRANCH" || true

# Push using ONLY the chosen key
GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes" git push -u origin "$BRANCH"
