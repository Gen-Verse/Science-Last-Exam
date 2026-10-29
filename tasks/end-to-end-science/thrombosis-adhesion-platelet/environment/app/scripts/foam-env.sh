#!/usr/bin/env bash
source /opt/openfoam9/etc/bashrc
export FOAM_USER_APPBIN=/opt/sle/bin FOAM_USER_LIBBIN=/opt/sle/lib
export PATH="$FOAM_USER_APPBIN:$PATH"
export LD_LIBRARY_PATH="$FOAM_USER_LIBBIN:$LD_LIBRARY_PATH"
export LC_ALL=C
