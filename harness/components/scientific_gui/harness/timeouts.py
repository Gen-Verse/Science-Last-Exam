"""Scale operational deadlines without changing requested GUI action durations."""
import math
import os


def scaled_timeout(seconds):
    factor = float(os.environ.get('SLE_TIMEOUT_MULTIPLIER', '1'))
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError('SLE_TIMEOUT_MULTIPLIER must be finite and positive')
    return seconds * factor
