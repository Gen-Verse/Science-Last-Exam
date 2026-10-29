"""Run inside Slicer; only the GUI event loop can refresh this readiness receipt.

The command-line Python script runs after module initialization. A visible main
window, initialized views, no splash/modal and two live Qt ticks are required.
See https://slicer.readthedocs.io/en/latest/developer_guide/script_repository.html
"""
import json
import os
from pathlib import Path
import time

import qt
import slicer

_receipt = Path(os.environ["SCIENCE_SLICER_READY_FILE"])
_nonce = os.environ["SCIENCE_SLICER_READY_NONCE"]
_ticks = 0


def heartbeat():
    global _ticks
    window = slicer.util.mainWindow()
    visible = bool(window and window.isVisible() and window.isEnabled()
                   and window.width >= 600 and window.height >= 400)
    splash = any(widget.inherits("QSplashScreen") and widget.isVisible()
                 for widget in slicer.app.topLevelWidgets())
    modules = slicer.app.moduleManager()
    initialized = bool(modules and modules.module("Volumes") and modules.module("Segmentations")
                       and slicer.app.layoutManager() and slicer.mrmlScene)
    ready = visible and initialized and not splash and slicer.app.activeModalWidget() is None
    _ticks = _ticks + 1 if ready else 0
    value = {"nonce": _nonce, "ready": ready, "consecutive_ready_ticks": _ticks,
             "monotonic": time.monotonic(), "pid": os.getpid(),
             "main_window_visible": visible, "views_initialized": initialized,
             "splash_visible": splash, "modal_active": slicer.app.activeModalWidget() is not None}
    temporary = _receipt.with_suffix(".tmp")
    temporary.write_text(json.dumps(value))
    temporary.replace(_receipt)


# Keep a strong reference for the lifetime of the application.
slicer._scienceReadyTimer = qt.QTimer()
slicer._scienceReadyTimer.setInterval(500)
slicer._scienceReadyTimer.connect("timeout()", heartbeat)
slicer._scienceReadyTimer.start()
