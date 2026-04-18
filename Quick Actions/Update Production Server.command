#!/bin/zsh

set -u

REPO_DIR="/Users/joshadams/Desktop/Coding Projects/mob-boss-code-main"
SSH_BIN="/usr/bin/ssh"
OSA_BIN="/usr/bin/osascript"
TARGET_HOST="root@134.199.226.15"
SSH_KEY="${HOME}/.ssh/id_ed25519"
CONTROL_SOCKET="/tmp/mobboss-prod-ssh-control"
DEPLOYED_COMMIT=""
MOBBOSS_RECOVERY_NEEDED="No"
FINAL_SYSTEMCTL_STATUS=""
FINAL_LOCAL_AUTH_RESULT=""
FINAL_PUBLIC_HTTP_RESULT=""

show_success() {
  "${OSA_BIN}" - "$1" <<'APPLESCRIPT'
on run argv
  display dialog (item 1 of argv) buttons {"OK"} default button "OK"
end run
APPLESCRIPT
}

show_error() {
  "${OSA_BIN}" - "$1" <<'APPLESCRIPT'
on run argv
  display dialog (item 1 of argv) buttons {"OK"} default button "OK" with icon stop
end run
APPLESCRIPT
}

log_section() {
  echo
  echo "== $1 =="
}

print_summary() {
  echo
  echo "Deployment summary:"
  echo "Deployed commit: ${DEPLOYED_COMMIT:-unknown}"
  echo "mobboss needed recovery: ${MOBBOSS_RECOVERY_NEEDED}"
  echo "Final systemctl status: ${FINAL_SYSTEMCTL_STATUS:-unknown}"
  echo "Final local /auth/ result: ${FINAL_LOCAL_AUTH_RESULT:-unknown}"
  echo "Final public HTTP result: ${FINAL_PUBLIC_HTTP_RESULT:-unknown}"
}

fail_deploy() {
  print_summary
  show_error "Error: $1"
  exit 1
}

diagnose_remote_dns() {
  log_section "Remote DNS Diagnostics"
  run_remote_allow_fail "cat /etc/resolv.conf"
  run_remote_allow_fail "getent hosts github.com"
  run_remote_allow_fail "getent hosts deb.debian.org"
}

cleanup_ssh_master() {
  "${SSH_BIN}" -O exit -o ControlPath="${CONTROL_SOCKET}" "${TARGET_HOST}" >/dev/null 2>&1 || true
  rm -f "${CONTROL_SOCKET}" >/dev/null 2>&1 || true
}

trap cleanup_ssh_master EXIT

if [[ ! -f "${REPO_DIR}/documentation/deployment/README.md" ]]; then
  show_error "Error: Missing documentation/deployment/README.md"
  exit 1
fi

log_section "Deployment Runbook"
sed -n '1,240p' "${REPO_DIR}/documentation/deployment/README.md"

if [[ ! -f "${SSH_KEY}" ]]; then
  show_error "Error: SSH key not found at ${SSH_KEY}"
  exit 1
fi

SSH_ARGS=(
  -tt
  -i "${SSH_KEY}"
  -o BatchMode=no
  -o StrictHostKeyChecking=accept-new
  -o ControlMaster=auto
  -o ControlPersist=600
  -o ControlPath="${CONTROL_SOCKET}"
)

log_section "SSH Connection"
echo "Opening reusable SSH session to ${TARGET_HOST}"
if ! "${SSH_BIN}" "${SSH_ARGS[@]}" "${TARGET_HOST}" "exit" 2>&1; then
  show_error "Error: Could not open SSH session to ${TARGET_HOST}. If key auth is not accepted, enter the server password when prompted in Terminal."
  exit 1
fi

run_remote() {
  local cmd="$1"
  local output

  echo
  echo "\$ ${cmd}"
  output="$("${SSH_BIN}" "${SSH_ARGS[@]}" "${TARGET_HOST}" "${cmd}" 2>&1)"
  local exit_code=$?
  printf '%s\n' "${output}"
  if [[ ${exit_code} -ne 0 ]]; then
    if [[ "${output}" == *"Could not resolve host: github.com"* ]]; then
      diagnose_remote_dns
    fi
    fail_deploy "Command failed: ${cmd}

${output}"
  fi
  REPLY="${output}"
}

run_remote_allow_fail() {
  local cmd="$1"
  local output

  echo
  echo "\$ ${cmd}"
  output="$("${SSH_BIN}" "${SSH_ARGS[@]}" "${TARGET_HOST}" "${cmd}" 2>&1)"
  local exit_code=$?
  printf '%s\n' "${output}"
  REPLY="${output}"
  return ${exit_code}
}

extract_commit_hash() {
  local text="$1"
  local hash
  hash="$(printf '%s\n' "${text}" | grep -Eo '[0-9a-f]{7,40}' | tail -n 1 || true)"
  if [[ -n "${hash}" ]]; then
    DEPLOYED_COMMIT="${hash}"
  fi
}

check_mobboss_health() {
  log_section "mobboss Health Checks"

  run_remote "cd /root/mob-boss-code-main && systemctl status mobboss --no-pager -l"
  local status_output="${REPLY}"
  FINAL_SYSTEMCTL_STATUS="$(printf '%s\n' "${status_output}" | grep -m1 'Active:' | sed 's/^[[:space:]]*//')"

  run_remote_allow_fail "cd /root/mob-boss-code-main && ss -ltnp | grep 8000"
  local port_status=$?
  local port_output="${REPLY}"

  run_remote "cd /root/mob-boss-code-main && curl -I --max-time 5 http://127.0.0.1:8000/auth/"
  local curl_output="${REPLY}"
  FINAL_LOCAL_AUTH_RESULT="$(printf '%s\n' "${curl_output}" | grep -m1 '^HTTP/' || true)"

  if [[ "${status_output}" == *"active (running)"* && "${status_output}" != *"deactivating"* && ${port_status} -eq 0 && "${curl_output}" == *"HTTP/1.1 200 OK"* ]]; then
    return 0
  fi

  return 1
}

recover_mobboss() {
  MOBBOSS_RECOVERY_NEEDED="Yes"
  log_section "mobboss Recovery"

  run_remote "cd /root/mob-boss-code-main && systemctl status mobboss --no-pager -l"
  if [[ "${REPLY}" == *"deactivating (stop-sigterm)"* ]]; then
    echo
    echo "Service is deactivating. Waiting briefly before retry."
    sleep 5
    run_remote "cd /root/mob-boss-code-main && systemctl status mobboss --no-pager -l"
  fi

  run_remote_allow_fail "cd /root/mob-boss-code-main && ss -ltnp | grep 8000"
  if [[ $? -eq 0 ]]; then
    local stale_pid
    stale_pid="$(printf '%s\n' "${REPLY}" | grep -Eo 'pid=[0-9]+' | head -n 1 | cut -d= -f2 || true)"
    if [[ -n "${stale_pid}" ]]; then
      echo
      echo "Clearing stale process on port 8000: PID ${stale_pid}"
      run_remote "cd /root/mob-boss-code-main && kill -TERM ${stale_pid}"
      sleep 3
      run_remote_allow_fail "cd /root/mob-boss-code-main && ss -ltnp | grep 8000"
      if [[ $? -eq 0 ]]; then
        run_remote "cd /root/mob-boss-code-main && kill -KILL ${stale_pid}"
        sleep 2
      fi
    fi
  fi

  run_remote_allow_fail "cd /root/mob-boss-code-main && ss -ltnp | grep 8000"
  if [[ $? -eq 0 ]]; then
    fail_deploy "Port 8000 is still busy after recovery attempt."
  fi

  run_remote "cd /root/mob-boss-code-main && systemctl start mobboss"

  if ! check_mobboss_health; then
    fail_deploy "mobboss health checks still failing after recovery."
  fi
}

log_section "Deployment"

run_remote "cd /root/mob-boss-code-main && git pull --ff-only origin main"
extract_commit_hash "${REPLY}"

run_remote "cd /root/mob-boss-code-main && npm run build"
run_remote "cd /root/mob-boss-code-main && /root/mob-boss-code-main/venv/bin/python3 project/mobboss_apps/manage.py collectstatic --noinput"
run_remote "cd /root/mob-boss-code-main && mkdir -p /var/www/mobboss/static"
run_remote "cd /root/mob-boss-code-main && rsync -av --delete /root/mob-boss-code-main/project/mobboss_apps/staticfiles/ /var/www/mobboss/static/"
run_remote "cd /root/mob-boss-code-main && systemctl restart mobboss"

if ! check_mobboss_health; then
  recover_mobboss
fi

log_section "nginx And Public Health"
run_remote "cd /root/mob-boss-code-main && systemctl restart nginx"
run_remote "cd /root/mob-boss-code-main && nginx -t"
run_remote "cd /root/mob-boss-code-main && curl -I --max-time 5 http://134.199.226.15/"
FINAL_PUBLIC_HTTP_RESULT="$(printf '%s\n' "${REPLY}" | grep -m1 '^HTTP/' || true)"

if [[ "${FINAL_PUBLIC_HTTP_RESULT}" != "HTTP/1.1 302 Found" ]]; then
  fail_deploy "Public health check did not return HTTP/1.1 302 Found."
fi

if [[ -z "${DEPLOYED_COMMIT}" ]]; then
  run_remote "cd /root/mob-boss-code-main && git rev-parse HEAD"
  DEPLOYED_COMMIT="$(printf '%s\n' "${REPLY}" | tail -n 1)"
fi

print_summary
show_success "Server Update Successful"
