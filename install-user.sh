#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")" && pwd)"
applications_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons_dir="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

mkdir -p "$applications_dir" "$icons_dir"
install -m 0644 "$project_dir/assets/sdeck.svg" "$icons_dir/sdeck.svg"

sed "s|@PROJECT_DIR@|$project_dir|g" "$project_dir/packaging/sdeck.desktop.in" > "$applications_dir/sdeck.desktop"
chmod 0644 "$applications_dir/sdeck.desktop"
if [[ "${1:-}" == "--autostart" ]]; then
  autostart_dir="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
  mkdir -p "$autostart_dir"
  cp "$applications_dir/sdeck.desktop" "$autostart_dir/sdeck.desktop"
  echo "YASDEC instalado en el menú de aplicaciones y configurado para iniciar con la sesión."
else
  echo "YASDEC instalado en el menú de aplicaciones."
fi
