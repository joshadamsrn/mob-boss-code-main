#!/bin/zsh

set -u

SSH_DIR="${HOME}/.ssh"
SSH_CONFIG="${SSH_DIR}/config"
OSA_BIN="/usr/bin/osascript"

show_success() {
  "${OSA_BIN}" - "$1" <<'APPLESCRIPT'
on run argv
  display dialog (item 1 of argv) buttons {"OK"} default button "OK"
end run
APPLESCRIPT
}

mkdir -p "${SSH_DIR}"
chmod 700 "${SSH_DIR}"
touch "${SSH_CONFIG}"
chmod 600 "${SSH_CONFIG}"

if ! grep -q "^Host mobboss-prod$" "${SSH_CONFIG}" 2>/dev/null; then
  cat >> "${SSH_CONFIG}" <<'EOF'

Host mobboss-prod
  HostName 134.199.226.15
  User root
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
EOF
fi

show_success "Configured SSH alias 'mobboss-prod' for 134.199.226.15"
