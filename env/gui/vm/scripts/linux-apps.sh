#!/usr/bin/env bash
set -euo pipefail
asset() { python3 -c 'import json,sys; from pathlib import Path; a=json.load(open("settings.json"))["assets"][sys.argv[1]]; print(Path("installers").resolve()/a["filename"] if sys.argv[2]=="path" else a[sys.argv[2]])' "$1" "$2"; }
for pair in 'freecad_11 freecad-1.1 freecad-1.1.0'; do
  read -r name launcher folder <<< "$pair"
  python3 harness/images/install-freecad.py --appimage "$(asset "$name" path)" \
    --sha256 "$(asset "$name" sha256)" --prefix "$HOME/.local/opt/$folder" --launcher-name "$launcher"
done
mkdir -p "$HOME/build/kicad"
tar -xf "$(asset kicad path)" -C "$HOME/build/kicad"
mapfile -t appimages < <(find "$HOME/build/kicad" -type f -name '*.AppImage')
if [[ ${#appimages[@]} != 1 ]]; then echo 'Expected exactly one KiCad AppImage in the verified archive' >&2; exit 1; fi
# The enclosing tar's SHA-256 was verified before transfer into the guest.
appimage_sha=$(sha256sum "${appimages[0]}" | cut -d ' ' -f 1)
python3 harness/images/install-kicad.py --appimage "${appimages[0]}" --sha256 "$appimage_sha" \
  --prefix "$HOME/.local/opt/kicad-10.0.2"
sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y "$(asset chimerax path)"
if ! python3 -m pip install --user --only-binary=:all: \
  --find-links https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-22.04/ wxPython==4.2.2; then
  sudo -n apt-get install -y libgtk-3-dev libnotify-dev libsdl2-dev libwebkit2gtk-4.0-dev \
    libgstreamer-plugins-base1.0-dev libsm-dev libxtst-dev
  python3 -m pip install --user --no-binary=wxPython wxPython==4.2.2
fi
# Fixed release; build in user-owned paths so the GUI hook installer can update its files.
git clone --depth 1 --branch 8.4.1 https://github.com/OSGeo/grass.git "$HOME/build/grass-8.4.1"
(
  cd "$HOME/build/grass-8.4.1"
  ./configure --prefix="$HOME/.local" --with-cxx --with-python=/usr/bin/python3 \
    --with-wxwidgets=/usr/bin/wx-config --without-postgres --without-mysql --without-pdal
  make -j"${BUILD_JOBS:-2}"
  make install
)
bash harness/images/linux-desktop-v1/build-celestia.sh \
  "$HOME/build/celestia-http" "$HOME/.local/opt/celestia-http"
mkdir -p /home/user/grassdata
# Empty bootstrap location; each task imports its bundled synthetic data.
grass -c EPSG:4326 /home/user/grassdata/world_latlong_wgs84 -e
