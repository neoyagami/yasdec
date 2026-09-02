#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "This installer must be run through pkexec or sudo." >&2
  exit 1
fi

mode="install"
if [[ "${1:-}" == "--remove" ]]; then
  mode="remove"
  shift
fi

target_user="${1:-}"
if [[ -z "$target_user" ]] || ! id "$target_user" >/dev/null 2>&1; then
  echo "A valid desktop user is required." >&2
  exit 1
fi

script_dir="$(cd "$(dirname "$0")" && pwd)"
rule_target="/etc/udev/rules.d/70-sdeck-uinput.rules"
module_target="/etc/modules-load.d/sdeck-uinput.conf"

if [[ "$mode" == "remove" ]]; then
  rm -f "$rule_target" "$module_target"
  if getent group sdeck-input >/dev/null 2>&1; then
    gpasswd --delete "$target_user" sdeck-input >/dev/null 2>&1 || true
  fi
  udevadm control --reload-rules
  echo "YASDEC uinput permissions removed. Sign out and back in to refresh group membership."
  exit 0
fi

groupadd --system --force sdeck-input
usermod --append --groups sdeck-input "$target_user"
install -D -m 0644 "$script_dir/70-sdeck-uinput.rules" "$rule_target"
install -D -m 0644 "$script_dir/sdeck-uinput.conf" "$module_target"
modprobe uinput
udevadm control --reload-rules
udevadm trigger --subsystem-match=misc --sysname-match=uinput || true

echo "YASDEC uinput permissions installed for $target_user."
echo "Sign out and back in before using virtual keyboard actions."
