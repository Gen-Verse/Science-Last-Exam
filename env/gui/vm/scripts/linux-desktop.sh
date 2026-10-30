#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/Desktop" "$HOME/build" "$HOME/.local/bin" "$HOME/.config/autostart"
sudo -n mkdir -p /etc/gdm3
sudo -n tee /etc/gdm3/custom.conf >/dev/null <<'GDM'
[daemon]
WaylandEnable=false
AutomaticLoginEnable=true
AutomaticLogin=user
GDM
sudo -n systemctl set-default graphical.target
sudo -n timedatectl set-timezone UTC
dbus-run-session -- gsettings set org.gnome.desktop.session idle-delay 0
dbus-run-session -- gsettings set org.gnome.desktop.screensaver lock-enabled false
dbus-run-session -- gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'
cat > "$HOME/.local/bin/scientific-software-operation-display" <<'DISPLAY'
#!/bin/sh
output=$(xrandr --query | awk '$2 == "connected" {print $1; exit}')
test -n "$output" && xrandr --output "$output" --mode 1920x1080
DISPLAY
chmod +x "$HOME/.local/bin/scientific-software-operation-display"
cat > "$HOME/.config/autostart/scientific-software-operation-display.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=Scientific desktop resolution
Exec=$HOME/.local/bin/scientific-software-operation-display
Terminal=false
ENTRY
# Desktop PATH must include the versioned application launchers.
printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.profile"
