#!/bin/zsh

set -u

REPO_DIR="/Users/joshadams/Desktop/Coding Projects/mob-boss-code-main"
OSA_BIN="/usr/bin/osascript"
DEPLOY_SCRIPT="${REPO_DIR}/Quick Actions/Update Production Server.command"

show_success() {
  "${OSA_BIN}" - "$1" >/dev/null <<'APPLESCRIPT'
on run argv
  display dialog (item 1 of argv) buttons {"OK"} default button "OK"
end run
APPLESCRIPT
}

ask_post_push_action() {
  "${OSA_BIN}" <<'APPLESCRIPT'
set dialogResult to display dialog "Push Completed Successfully" buttons {"OK", "Update Server"} default button "Update Server"
button returned of dialogResult
APPLESCRIPT
}

show_error() {
  "${OSA_BIN}" - "$1" >/dev/null <<'APPLESCRIPT'
on run argv
  display dialog (item 1 of argv) buttons {"OK"} default button "OK" with icon stop
end run
APPLESCRIPT
}

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
  show_error "Error: Could not determine the current Git branch."
  exit 1
fi

if [[ -z "${git_name}" || -z "${git_email}" ]]; then
  echo "Git identity is not configured on this machine."
  echo "Run 'Set Git Identity.command' first."
  echo
  show_error "Error: Git identity is not configured on this machine. Run 'Set Git Identity.command' first."
  exit 1
fi

if [[ -z "${remote_url}" ]]; then
  echo "Remote 'origin' is not configured."
  show_error "Error: Remote 'origin' is not configured."
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
  show_success "No changes to commit."
  exit 0
fi

commit_output="$(git commit -m "${commit_message}" 2>&1)"
commit_exit=$?
if [[ ${commit_exit} -ne 0 ]]; then
  echo
  echo "Commit failed."
  echo "${commit_output}"
  show_error "Error: ${commit_output}"
  exit ${commit_exit}
fi

push_output="$(git push origin "${branch_name}" 2>&1)"
push_exit=$?
if [[ ${push_exit} -ne 0 ]]; then
  echo
  echo "Push failed."
  echo "If this is a new machine, run 'Trust GitHub SSH Host.command' and make sure your SSH key is loaded."
  echo "${push_output}"
  show_error "Error: ${push_output}"
  exit ${push_exit}
fi

echo
echo "Push completed."
post_push_action="$(ask_post_push_action)"
if [[ "${post_push_action}" == "Update Server" ]]; then
  if [[ ! -f "${DEPLOY_SCRIPT}" ]]; then
    show_error "Error: Missing Update Production Server.command"
    exit 1
  fi
  "${DEPLOY_SCRIPT}"
  exit $?
fi

show_success "Push Completed Successfully"
