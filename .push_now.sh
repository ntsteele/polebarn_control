#!/usr/bin/env bash
set -e
cd ~/polebarn_control

# use SSH remote
git remote set-url origin git@github.com:ntsteele/polebarn_control.git

# avoid host prompt
mkdir -p ~/.ssh
ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null

# pick a key (override by: KEY=/path/to/key ./ .push_now.sh)
KEY="${KEY:-$HOME/.ssh/polebarn_control}"
[ -f "$KEY" ] || KEY="$HOME/.ssh/id_ed25519"
[ -f "$KEY" ] || KEY="$HOME/.ssh/id_rsa"
echo "Using key: $KEY" >&2

# commit & push using ONLY that key
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git add -A
git commit -m "update" || true
GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes" git pull --rebase origin "$BRANCH" || true
GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes" git push -u origin "$BRANCH"
