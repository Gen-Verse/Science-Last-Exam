"""Host environment lookup; no personal application storage."""
import os
def credentials():
    key=os.environ.get('NOVITA_API_KEY') or os.environ.get('MODEL_API_KEY')
    if not key:raise RuntimeError('Set NOVITA_API_KEY or MODEL_API_KEY in the host environment')
    return key
