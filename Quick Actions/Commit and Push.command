#!/bin/zsh

set -u

REPO_DIR="/Users/joshadams/Desktop/Coding Projects/mob-boss-code-main"

cd "${REPO_DIR}" || exit 1

clear
echo "Commit and push current branch"
echo

branch_name="$(git branch --show-current)"
remote_url="$(git remote get-url origin 2>/dev/null)"
git_name="$(git config --get user.name || true)"
git_email="$(git config --get user.email || true)"

if [[ -z "${branch_name}" ]]; then
  echo "Could not determine the current branch."
  read "pause?Press Enter to close..."
  exit 1
fi

if [[ -z "${git_name}" || -z "${git_email}" ]]; then
  echo "Git identity is not configured on this machine."
  echo "Run 'Set Git Identity.command' first."
  echo
  read "pause?Press Enter to close..."
  exit 1
fi

if [[ -z "${remote_url}" ]]; then
  echo "Remote 'origin' is not configured."
  read "pause?Press Enter to close..."
  exit 1
fi

echo "Repo:   ${REPO_DIR}"
echo "Branch: ${branch_name}"
echo "Remote: ${remote_url}"
echo
echo "Git status:"
git status --short
echo
commit_message="Mob Boss update $(date '+%Y-%m-%d %H:%M')"
echo "Commit message: ${commit_message}"
echo

git add -A

if git diff --cached --quiet; then
  echo
  echo "No staged changes to commit."
  read "pause?Press Enter to close..."
  exit 0
fi

if ! git commit -m "${commit_message}"; then
  echo
  echo "Commit failed."
  read "pause?Press Enter to close..."
  exit 1
fi

if ! git push origin "${branch_name}"; then
  echo
  echo "Push failed."
  echo "If this is a new machine, run 'Trust GitHub SSH Host.command' and make sure your SSH key is loaded."
  read "pause?Press Enter to close..."
  exit 1
fi

echo
echo "Push completed."
read "pause?Press Enter to close..."
