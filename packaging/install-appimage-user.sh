#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  echo "Install the AppImage as your regular desktop user, without sudo." >&2
  exit 2
fi

mode="${1:-}"
source_appimage="${2:-}"
desktop_template="${3:-}"
icon_source="${4:-}"
shift $(( $# < 4 ? $# : 4 ))

data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
install_dir="$data_home/yasdec"
installed_appimage="$install_dir/YASDEC-x86_64.AppImage"
applications_dir="$data_home/applications"
icons_dir="$data_home/icons/hicolor/scalable/apps"
desktop_file="$applications_dir/sdeck.desktop"
autostart_file="$config_home/autostart/sdeck.desktop"

refresh_desktop_database() {
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$applications_dir" >/dev/null 2>&1 || true
  fi
}

if [[ "$mode" == "uninstall" ]]; then
  rm -f -- "$desktop_file" "$autostart_file" "$icons_dir/sdeck.svg" "$installed_appimage"
  rmdir -- "$install_dir" 2>/dev/null || true
  refresh_desktop_database
  echo "YASDEC was removed from this user account. Personal configuration was kept."
  exit 0
fi

if [[ "$mode" != "install" ]] || [[ ! -f "$source_appimage" ]] || \
   [[ ! -f "$desktop_template" ]] || [[ ! -f "$icon_source" ]]; then
  echo "The AppImage installation files are incomplete." >&2
  exit 1
fi

enable_autostart=false
for argument in "$@"; do
  case "$argument" in
    --autostart) enable_autostart=true ;;
    *) echo "Unknown install option: $argument" >&2; exit 2 ;;
  esac
done

mkdir -p "$install_dir" "$applications_dir" "$icons_dir"
if [[ "$(readlink -f "$source_appimage")" != "$(readlink -f "$installed_appimage" 2>/dev/null || true)" ]]; then
  install -m 0755 "$source_appimage" "$installed_appimage.new"
  mv -f -- "$installed_appimage.new" "$installed_appimage"
fi
install -m 0644 "$icon_source" "$icons_dir/sdeck.svg"

escaped_exec="${installed_appimage//\\/\\\\}"
escaped_exec="${escaped_exec//\"/\\\"}"
escaped_exec="${escaped_exec//&/\\&}"
escaped_exec="${escaped_exec//|/\\|}"
sed "s|^Exec=.*|Exec=\"$escaped_exec\"|" "$desktop_template" > "$desktop_file.new"
chmod 0644 "$desktop_file.new"
mv -f -- "$desktop_file.new" "$desktop_file"

if [[ "$enable_autostart" == true ]]; then
  mkdir -p "$(dirname "$autostart_file")"
  sed "s|^Exec=.*|Exec=\"$escaped_exec\" --background|" "$desktop_template" > "$autostart_file.new"
  chmod 0644 "$autostart_file.new"
  mv -f -- "$autostart_file.new" "$autostart_file"
fi

refresh_desktop_database
if [[ "$enable_autostart" == true ]]; then
  echo "YASDEC was installed for this user and will start with the desktop session."
else
  echo "YASDEC was installed for this user and added to the application menu."
fi
