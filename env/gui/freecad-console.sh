#!/bin/sh
set -eu
unset PYTHONHOME PYTHONPATH QT_PLUGIN_PATH QML2_IMPORT_PATH LD_LIBRARY_PATH
export QT_QPA_PLATFORM=offscreen
exec xvfb-run -a /opt/freecad/AppRun "$@"
