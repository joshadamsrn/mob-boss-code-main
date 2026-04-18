#!/bin/zsh

set -u

clear
echo "Trust GitHub SSH host key for this machine"
echo
echo "This adds GitHub to ~/.ssh/known_hosts if needed."
echo

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

if ssh-keygen -F github.com >/dev/null 2>&1; then
  echo "GitHub host key is already present in ~/.ssh/known_hosts"
else
  ssh-keyscan github.com >> "${HOME}/.ssh/known_hosts"
  chmod 600 "${HOME}/.ssh/known_hosts"
  echo "Added GitHub host key to ~/.ssh/known_hosts"
fi

echo
echo "Current GitHub entries:"
ssh-keygen -F github.com || true
echo
read "pause?Press Enter to close..."
