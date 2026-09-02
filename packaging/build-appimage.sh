#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${SDECK_APPIMAGE_BUILD_DIR:-$project_dir/build/appimage}"
app_dir="$build_root/AppDir"
dist_dir="$build_root/pyinstaller"
output="${SDECK_APPIMAGE_OUTPUT:-$project_dir/dist/YASDEC-x86_64.AppImage}"
temporary_output="$output.new"
python_command="${SDECK_BUILD_PYTHON:-python3}"
appimagetool_command="${APPIMAGETOOL:-appimagetool}"

if ! "$python_command" -c 'import PyInstaller' >/dev/null 2>&1; then
  echo "PyInstaller is required. Install requirements-build.txt in a build environment." >&2
  exit 1
fi
if ! command -v "$appimagetool_command" >/dev/null 2>&1 && [[ ! -x "$appimagetool_command" ]]; then
  echo "appimagetool was not found. Set APPIMAGETOOL to its executable path." >&2
  exit 1
fi

rm -rf "$app_dir" "$dist_dir"
mkdir -p "$app_dir/usr/lib/sdeck" "$app_dir/usr/share/sdeck" \
  "$app_dir/usr/share/licenses/yasdec" "$dist_dir" "$(dirname "$output")"

"$python_command" -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --name YASDEC \
  --distpath "$dist_dir" \
  --workpath "$build_root/work" \
  --specpath "$build_root" \
  --paths "$project_dir" \
  --add-data "$project_dir/assets:assets" \
  --collect-all StreamDeck \
  "$project_dir/packaging/appimage_entry.py"

cp -a "$dist_dir/YASDEC/." "$app_dir/usr/lib/sdeck/"
install -m 0755 "$project_dir/packaging/AppRun" "$app_dir/AppRun"
install -m 0644 "$project_dir/packaging/sdeck.appimage.desktop" "$app_dir/sdeck.desktop"
install -m 0644 "$project_dir/assets/sdeck.svg" "$app_dir/sdeck.svg"
install -m 0755 "$project_dir/packaging/install-uinput.sh" "$app_dir/usr/share/sdeck/install-uinput.sh"
install -m 0644 "$project_dir/packaging/70-sdeck-uinput.rules" "$app_dir/usr/share/sdeck/70-sdeck-uinput.rules"
install -m 0644 "$project_dir/packaging/sdeck-uinput.conf" "$app_dir/usr/share/sdeck/sdeck-uinput.conf"
install -m 0644 "$project_dir/LICENSE" "$app_dir/usr/share/licenses/yasdec/LICENSE"

ARCH=x86_64 "$appimagetool_command" "$app_dir" "$temporary_output"
mv -f "$temporary_output" "$output"
sha256sum "$output" > "$output.sha256"
echo "Created $output"
