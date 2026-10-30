"""Distinguish bounded observation failure from the task wall deadline.

Only read-only observation is handled here. Never retry a GUI action.
"""
import time
from harness.timeouts import scaled_timeout
from .transport import IndeterminateGUI

class ObservationWallTimeout(TimeoutError):
    wall_budget_exhausted = True


class ObservationFailure(RuntimeError):
    failure_category = 'environment_error'
    failure_phase = 'observation'


def observe_before_deadline(backend, version, remaining):
    attempt_start = len(getattr(backend.transport, "attempts", ()))
    try:
        return backend.observe(version)
    except IndeterminateGUI:
        raise
    except (TimeoutError, RuntimeError) as exc:
        if getattr(backend.transport, "uncertain_execute", False):
            raise
        last_error = getattr(backend.transport, 'last_error', None) or {}
        timed_out_capture = (str(exc) == 'No real guest screenshot returned'
                             and last_error.get('kind') == 'ReadTimeout')
        # execute() resets transport.read_only in finally. Inspect only an
        # attempt made during this observation, not that reset flag or an old
        # query's error. No action or indeterminate execution is converted.
        attempts = getattr(backend.transport, "attempts", ())
        latest = attempts[-1] if len(attempts) > attempt_start else {}
        timed_out_query = (
            str(exc) == 'Read-only controller query not confirmed after bounded attempts'
            and last_error.get('kind') == 'ReadTimeout'
            and latest.get('read_only') is True
            and latest.get('confirmed') is False
            and latest.get('uncertain_execute') is False
            and latest.get('error') == last_error
            and not getattr(backend.transport, 'uncertain_execute', False)
        )
        # Engine.observe caps each observation at 60 seconds. Only a known
        # timeout at the actual episode deadline is a normal wall-budget stop.
        # Socket reads can finish early; classify that as an observation failure
        # without sleeping, retrying inputs, or claiming the wall has elapsed.
        if (remaining <= scaled_timeout(60) and time.monotonic() >= backend.budget.deadline
                and (isinstance(exc, TimeoutError) or timed_out_capture or timed_out_query)):
            raise ObservationWallTimeout('GUI wall budget expired during read-only observation') from exc
        raise ObservationFailure(str(exc)) from exc
