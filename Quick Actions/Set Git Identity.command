#!/bin/zsh

set -u

clear
echo "Set global Git identity"
echo

read "git_name?Git user.name: "
read "git_email?Git user.email: "

if [[ -z "${git_name}" || -z "${git_email}" ]]; then
  echo
  echo "Name and email are required."
  read "pause?Press Enter to close..."
  exit 1
fi

git config --global user.name "${git_name}"
git config --global user.email "${git_email}"

echo
echo "Saved:"
echo "  user.name  = $(git config --global --get user.name)"
echo "  user.email = $(git config --global --get user.email)"
echo
read "pause?Press Enter to close..."
